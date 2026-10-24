package dev.kakaofilter.core

import org.junit.Assert.*
import org.junit.Test

class BubbleDetectorTest {
    private val viewport=Box(0,100,400,700)
    private fun frame(offset: Int=0,changed: Boolean=false): PixelFrame {
        val pixels=IntArray(400*800) { 0xffb9cddb.toInt() }
        fun fill(box: Box,color: Int) { for (y in box.top until box.bottom) for (x in box.left until box.right) pixels[y*400+x]=color }
        fill(Box(60,150+offset,350,200+offset),0xffffffff.toInt())
        fill(Box(60,215+offset,260,275+offset),0xffffffff.toInt())
        fill(Box(170,300+offset,390,350+offset),0xffffe900.toInt())
        fill(Box(15,140+offset,45,175+offset),0xffffffff.toInt()) // Avatar is not a bubble.
        fill(Box(15,710,385,770),0xffffffff.toInt()) // Input is outside viewport.
        fill(Box(75,165+offset,if (changed) 110 else 100,175+offset),0xff222222.toInt())
        fill(Box(80,235+offset,150,245+offset),0xff222222.toInt())
        return PixelFrame(400,800,pixels)
    }
    @Test fun findsConsecutiveWhiteBubblesAndOutgoingContextWithoutAccessibilityBodyNodes() {
        val bubbles=BubbleDetector.find(frame(),viewport,1f)
        assertEquals(3,bubbles.size)
        assertEquals(listOf(true,true,false),bubbles.map { it.incoming })
        val nodes=listOf(
            UiNode(Box(12,125,52,165),id="profile",className="android.widget.ImageView"),
            UiNode(Box(60,125,160,143),id="nickname",text="대상"))+
            bubbles.map { UiNode(it.bounds,id="bubble",className="android.view.View",outgoing=!it.incoming) }
        val result=FilterEngine.evaluate(nodes,viewport,1f,null,Rules(true,listOf("대상"),allChats=true))
        assertEquals(2,result.masks.size)
        assertTrue(result.masks.any { it.top<=215 && it.bottom>=275 })
        assertFalse(result.masks.any { it.top>=300 })
    }
    @Test fun visualFingerprintSurvivesScrollButNotChangedMessagePixels() {
        val keys=BubbleFingerprints()
        val original=frame();val shifted=frame(-30);val changed=frame(changed=true)
        val first=BubbleDetector.find(original,viewport,1f).first()
        val moved=BubbleDetector.find(shifted,viewport,1f).first()
        assertEquals(keys.key(original,first,1f),keys.key(shifted,moved,1f))
        assertNotEquals(keys.key(original,first,1f),keys.key(changed,first,1f))
        assertNotEquals(keys.key(original,first,1f),BubbleFingerprints().key(original,first,1f))
    }
    @Test fun windowOffsetAndViewportClipAreRespected() {
        val original=frame()
        val offset=original.copy(left=20,top=30)
        val expected=BubbleDetector.find(original,viewport,1f).map { it.bounds }
        val actual=BubbleDetector.find(offset,Box(20,130,420,730),1f).map { it.bounds }
        assertEquals(expected.map { Box(it.left+20,it.top+30,it.right+20,it.bottom+30) },actual)
    }
    @Test fun clippedBubbleReusesActualPixelRowFingerprintsAfterItsSenderDisappears() {
        fun image(offset: Int): PixelFrame {
            val pixels=IntArray(400*800) { 0xffb9cddb.toInt() }
            for (y in 150+offset until 270+offset) for (x in 60 until 350) pixels[y*400+x]=0xffffffff.toInt()
            for (y in 165+offset until 185+offset) for (x in 80 until 170) pixels[y*400+x]=0xff222222.toInt()
            for (y in 230+offset until 250+offset) for (x in 90 until 260) pixels[y*400+x]=0xff222222.toInt()
            return PixelFrame(400,800,pixels)
        }
        val keys=BubbleFingerprints()
        val full=image(0);val moved=image(-110)
        val whole=BubbleDetector.find(full,viewport,1f).single()
        val clipped=BubbleDetector.find(moved,viewport,1f).single()
        val a=keys.signature(full,whole,1f)!!;val b=keys.signature(moved,clipped,1f)!!
        assertEquals(100,clipped.bounds.top)
        assertEquals(a.rows.takeLast(b.rows.size),b.rows)
        val memory=MessageMemory()
        memory.apply("room",listOf(RememberedBubble(whole.bounds,a.key,MessageOwner.HIDDEN,a.rows)))
        val result=memory.apply("room",listOf(RememberedBubble(clipped.bounds,b.key,MessageOwner.UNKNOWN,b.rows,clippedTop=true,tracked=true)))
        assertEquals(1,result.reused)
        assertEquals(listOf(clipped.bounds),result.masks)
    }
}
