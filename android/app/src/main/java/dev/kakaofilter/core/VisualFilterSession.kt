package dev.kakaofilter.core

data class ReadBubble(val bounds: Box, val incoming: Boolean, val fingerprint: String?, val rows: List<Long> = emptyList(), val clippedTop: Boolean=false, val clippedBottom: Boolean=false)
data class VisualFilterResult(val filter: FilterResult, val nodes: List<UiNode>, val reused: Int, val remembered: Int, val bubbles: Int)

class VisualFilterSession {
    private val memory=MessageMemory()
    private var previousRules: Rules?=null
    fun clear() { memory.clear();previousRules=null }
    fun evaluate(scope: String, nodes: List<UiNode>, viewport: Box, density: Float, room: String?, rules: Rules, bubbles: List<ReadBubble>, previousMasks: List<Box> = emptyList()): VisualFilterResult {
        if (previousRules!=rules) { memory.clear();previousRules=rules }
        val allowed=rules.enabled && rules.rememberMessages && rules.hiddenUsers.isNotEmpty() &&
            (rules.allChats || (room!=null && normalized(room) in rules.selectedChats.map(::normalized)))
        if (!allowed) {
            memory.clear()
            return VisualFilterResult(FilterEngine.evaluate(nodes,viewport,density,room,rules),nodes,0,0,0)
        }
        val usable=bubbles.filter { bubble ->
            bubble.bounds.clip(viewport)!=null &&
                (rules.hideImages || nodes.none { it.visible && it.media && it.bounds.contains(bubble.bounds) })
        }.map { bubble ->
            if (nodes.any { it.visible && (it.editable || it.outgoing) && it.bounds.clip(bubble.bounds)?.let { overlap -> overlap.area>=bubble.bounds.area*.8 }==true }) bubble.copy(incoming=false)
            else bubble
        }
        val augmented=nodes+usable.map { UiNode(it.bounds,id="bubble",className="android.view.View",outgoing=!it.incoming) }
        val direct=FilterEngine.evaluate(augmented,viewport,density,room,rules)
        val observations=usable.mapNotNull { bubble ->
            val key=bubble.fingerprint ?: return@mapNotNull null
            val region=direct.regions.firstOrNull { bubble.bounds.top>=it.bounds.top && bubble.bounds.bottom<=it.bounds.bottom }
            val owner=when {
                !bubble.incoming -> MessageOwner.OTHER
                region==null -> MessageOwner.UNKNOWN
                region.hidden -> MessageOwner.HIDDEN
                else -> MessageOwner.OTHER
            }
            val tracked=previousMasks.any { it.clip(bubble.bounds)?.let { overlap -> overlap.area>=bubble.bounds.area*.9 }==true }
            RememberedBubble(bubble.bounds,key,owner,bubble.rows,bubble.clippedTop,bubble.clippedBottom,tracked)
        }
        val remembered=memory.apply(scope,observations)
        val pad=(density*2).toInt().coerceAtLeast(1)
        val candidates=direct.masks+remembered.masks.mapNotNull { Box(it.left-pad,it.top-pad,it.right+pad,it.bottom+pad).clip(viewport) }
        val masks=mutableListOf<Box>()
        candidates.distinct().sortedByDescending { it.area }.forEach { if (masks.none { other -> other.contains(it) }) masks+=it }
        return VisualFilterResult(direct.copy(masks=masks,reason=if (remembered.reused>0) "기억한 메시지를 현재 위치에 다시 가렸습니다" else direct.reason),augmented,remembered.reused,remembered.remembered,usable.count { it.incoming })
    }
}
