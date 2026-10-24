package dev.kakaofilter.core

enum class MessageOwner { HIDDEN, OTHER, UNKNOWN }
data class RememberedBubble(val bounds: Box, val fingerprint: String, val owner: MessageOwner, val rows: List<Long> = emptyList(), val clippedTop: Boolean=false, val clippedBottom: Boolean=false, val tracked: Boolean=false)
data class MemoryResult(val masks: List<Box>, val reused: Int, val remembered: Int)

/** Session-only, scoped fingerprints plus adjacent-message context; never screen coordinates. */
class MessageMemory(private val capacity: Int=2000) {
    private data class Context(val before: String?, val after: String?)
    private data class Entry(val contexts: MutableSet<Context>, val width: Int, val rows: List<Long>)
    private var scope: String?=null
    private val known=linkedMapOf<String,Entry>()
    private val conflicts=linkedSetOf<String>()
    fun clear() { scope=null;known.clear();conflicts.clear() }
    fun apply(chat: String, bubbles: List<RememberedBubble>): MemoryResult {
        if (scope!=chat) { clear();scope=chat }
        for (b in bubbles.filter { it.owner==MessageOwner.OTHER }) {
            known.remove(b.fingerprint);conflicts+=b.fingerprint
        }
        val counts=bubbles.groupingBy { it.fingerprint }.eachCount()
        bubbles.forEachIndexed { index,b ->
            if (b.owner==MessageOwner.HIDDEN && !b.clippedTop && !b.clippedBottom && b.fingerprint !in conflicts && counts[b.fingerprint]==1) {
                val context=Context(bubbles.getOrNull(index-1)?.fingerprint,bubbles.getOrNull(index+1)?.fingerprint)
                val entry=known.getOrPut(b.fingerprint) { Entry(linkedSetOf(),b.bounds.width,b.rows.toList()) }
                entry.contexts+=context
                if (entry.contexts.size>8) entry.contexts.remove(entry.contexts.first())
            }
        }
        while (known.size>capacity) known.remove(known.keys.first())
        while (conflicts.size>capacity) conflicts.remove(conflicts.first())
        var reused=0
        val masks=bubbles.mapIndexedNotNull { index,b ->
            if (b.owner==MessageOwner.HIDDEN) return@mapIndexedNotNull b.bounds
            if (b.owner==MessageOwner.OTHER || b.fingerprint in conflicts || counts[b.fingerprint]!=1) return@mapIndexedNotNull null
            val before=bubbles.getOrNull(index-1)?.fingerprint
            val after=bubbles.getOrNull(index+1)?.fingerprint
            val matched=if (b.clippedTop || b.clippedBottom) {
                // A translated mask plus an exact visible text-row sequence can
                // validate a partly offscreen bubble without retaining its image.
                b.tracked && b.rows.size>=12 && !(b.clippedTop && b.clippedBottom) && known.values.count { entry ->
                    entry.width==b.bounds.width && entry.rows.size>=b.rows.size &&
                        (if (b.clippedTop) entry.rows.takeLast(b.rows.size) else entry.rows.take(b.rows.size))==b.rows
                }==1
            } else known[b.fingerprint]?.let { entry -> b.tracked || entry.contexts.any { (before!=null && it.before==before) || (after!=null && it.after==after) } }==true
            if (matched) { reused++;b.bounds } else null
        }
        return MemoryResult(masks,reused,known.size)
    }
}

/** Move currently confirmed masks with measured scroll deltas rather than removing them. */
class ScrollingMasks {
    private var tracked: List<Box> = emptyList()
    val boxes: List<Box> get()=viewport?.let { clip -> tracked.mapNotNull { it.clip(clip) } }.orEmpty()
    private var viewport: Box?=null
    private var window: Int?=null
    fun clear() { tracked=emptyList();viewport=null;window=null }
    fun replace(boxes: List<Box>, viewport: Box, window: Int) {
        tracked=boxes.toList();this.viewport=viewport;this.window=window
    }
    fun scroll(window: Int, deltaY: Int): List<Box>? {
        val clip=viewport ?: return null
        if (window!=this.window || deltaY==0 || kotlin.math.abs(deltaY.toLong())>clip.height*2L) { clear();return null }
        tracked=tracked.map { Box(it.left,it.top-deltaY,it.right,it.bottom-deltaY) }
        return boxes
    }
}
