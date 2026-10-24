package dev.kakaofilter.core

import java.security.MessageDigest
import java.security.SecureRandom

data class PixelFrame(val width: Int, val height: Int, val pixels: IntArray, val left: Int=0, val top: Int=0) {
    init { require(width>0 && height>0 && pixels.size.toLong()==width.toLong()*height) }
    val bounds get()=Box(left,top,left+width,top+height)
    fun pixel(x: Int,y: Int)=pixels[(y-top)*width+x-left]
}

data class VisualBubble(val bounds: Box, val incoming: Boolean)
data class BubbleSignature(val key: String, val rows: List<Long>, val width: Int)

/** Light Kakao theme only: connected white/yellow bubble fills, never OCR. */
object BubbleDetector {
    private fun kind(color: Int): Int {
        val r=(color ushr 16) and 255; val g=(color ushr 8) and 255; val b=color and 255
        if (minOf(r,g,b)>=225 && maxOf(r,g,b)-minOf(r,g,b)<=30) return 1
        if (r>=220 && g>=180 && b<=110) return 2
        return 0
    }

    fun find(frame: PixelFrame, viewport: Box, density: Float): List<VisualBubble> {
        val area=viewport.clip(frame.bounds) ?: return emptyList()
        val w=area.width; val h=area.height
        if (w.toLong()*h>12_000_000) return emptyList()
        val types=ByteArray(w*h)
        for (y in 0 until h) for (x in 0 until w) types[y*w+x]=kind(frame.pixel(x+area.left,y+area.top)).toByte()
        val queue=IntArray(w*h)
        val found=mutableListOf<VisualBubble>()
        fun dp(n: Int)=(n*density).toInt().coerceAtLeast(1)
        for (start in types.indices) {
            val type=types[start]
            if (type.toInt()==0) continue
            var head=0; var tail=1
            queue[0]=start; types[start]=0
            var minX=w; var minY=h; var maxX=0; var maxY=0
            while (head<tail) {
                val p=queue[head++]; val x=p%w; val y=p/w
                minX=minOf(minX,x); maxX=maxOf(maxX,x); minY=minOf(minY,y); maxY=maxOf(maxY,y)
                fun add(n: Int) { if (types[n]==type) { types[n]=0;queue[tail++]=n } }
                if (x>0) add(p-1)
                if (x<w-1) add(p+1)
                if (y>0) add(p-w)
                if (y<h-1) add(p+w)
            }
            val b=Box(area.left+minX,area.top+minY,area.left+maxX+1,area.top+maxY+1)
            if (b.width<dp(12) || b.height<dp(14) || tail<b.area*.38) continue
            // An input bar, avatar, toolbar or isolated text pixels are not bubbles.
            if (type.toInt()==1 && b.left-viewport.left in dp(36)..dp(110)) found+=VisualBubble(b,true)
            if (type.toInt()==2 && viewport.right-b.right in 0..dp(24) && b.left-viewport.left>=dp(36)) found+=VisualBubble(b,false)
        }
        return found.sortedBy { it.bounds.top }
    }
}

/** Salted, exact visual fingerprints. Raw frames and message strings are not retained. */
class BubbleFingerprints {
    private val salt=ByteArray(32).also { SecureRandom().nextBytes(it) }
    fun key(frame: PixelFrame, bubble: VisualBubble, density: Float)=signature(frame,bubble,density)?.key
    fun signature(frame: PixelFrame, bubble: VisualBubble, density: Float): BubbleSignature? {
        val b=bubble.bounds
        // A clipped bubble must not learn a different message's partial image.
        if (!frame.bounds.contains(b)) return null
        val edge=(density*2).toInt().coerceAtLeast(1)
        if (b.width<=edge*2 || b.height<=edge*2) return null
        val digest=MessageDigest.getInstance("SHA-256")
        val rows=mutableListOf<Long>()
        digest.update(salt)
        digest.update("${b.width}:${b.height}:${bubble.incoming}:".toByteArray())
        // Quantize antialiasing, excluding rounded borders. Coordinates are not part of the key.
        for (y in b.top+edge until b.bottom-edge) {
            val row=MessageDigest.getInstance("SHA-256")
            row.update(salt)
            var ink=false
            var value=0;var count=0
            for (x in b.left+edge until b.right-edge) {
                val c=frame.pixel(x,y)
                val dark=((c ushr 16) and 255)+((c ushr 8) and 255)+(c and 255)<540
                ink=ink || dark
                value=(value shl 1) or if (dark) 1 else 0
                count++
                if (count==8) { digest.update(value.toByte());row.update(value.toByte());value=0;count=0 }
            }
            if (count>0) { val byte=(value shl (8-count)).toByte();digest.update(byte);row.update(byte) }
            if (ink) rows+=java.nio.ByteBuffer.wrap(row.digest()).long
        }
        return BubbleSignature(digest.digest().joinToString("") { "%02x".format(it) },rows,b.width)
    }
}
