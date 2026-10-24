package dev.kakaofilter.core

import java.text.Normalizer

fun normalized(value: String): String = Normalizer.normalize(value, Normalizer.Form.NFC).trim().replace(Regex("\\s+"), " ")

data class Box(val left: Int, val top: Int, val right: Int, val bottom: Int) {
    val width get() = right - left
    val height get() = bottom - top
    val area get() = width.toLong() * height
    fun contains(other: Box) = left <= other.left && top <= other.top && right >= other.right && bottom >= other.bottom
    fun clip(other: Box): Box? = Box(maxOf(left, other.left), maxOf(top, other.top), minOf(right, other.right), minOf(bottom, other.bottom)).takeIf { it.width > 0 && it.height > 0 }
}

data class UiNode(
    val bounds: Box,
    val id: String = "",
    val className: String = "android.widget.TextView",
    val text: String = "",
    val description: String = "",
    val parent: Int = -1,
    val leaf: Boolean = true,
    val editable: Boolean = false,
    val outgoing: Boolean = false,
    val scrollable: Boolean = false,
    val visible: Boolean = true
) {
    val role get() = id.substringAfterLast('/').lowercase()
    val media get() = className.endsWith("ImageView") || listOf("photo", "sticker", "emoticon", "image_message").any { role.contains(it) }
}

data class Rules(
    val enabled: Boolean = false,
    val hiddenUsers: List<String> = emptyList(),
    val selectedChats: List<String> = emptyList(),
    val allChats: Boolean = false,
    val hideImages: Boolean = true,
    val displayMode: String = "opaque"
)

data class FilterResult(val masks: List<Box>, val senders: Int, val matched: Int, val reason: String, val recognizedNames: List<String> = emptyList(), val unnamedProfiles: Int = 0, val clippedProfiles: Int = 0)

/** Stateless: ownership is established again from the current accessibility tree. */
object FilterEngine {
    private val senderIds = setOf("sender_name", "chat_message_name", "message_name", "chatting_name", "profile_name", "nickname", "nick_name", "tv_nickname", "tv_name")
    private val messageIds = setOf("message", "message_text", "chat_message", "chat_message_text", "message_content", "chat_content", "bubble", "bubble_layout", "message_container", "chat_item_content", "reply_message", "photo", "image_message", "sticker", "emoticon")
    private val timeText=Regex("(?:오전|오후)?\\s*\\d{1,2}:\\d{2}")
    private val countText=Regex("\\d{1,3}")
    private fun hasContent(node: UiNode): Boolean {
        val content=node.text.ifBlank { node.description }
        return content.isNotBlank() && !timeText.matches(content) && !countText.matches(content)
    }
    private data class Anchor(val y: Int, val name: String?, val header: Box, val left: Int, val clipped: Boolean)

    fun evaluate(nodes: List<UiNode>, viewport: Box, density: Float, room: String?, rules: Rules): FilterResult {
        if (!rules.enabled || rules.hiddenUsers.isEmpty()) return FilterResult(emptyList(), 0, 0, "필터가 꺼져 있거나 숨김 목록이 비어 있습니다")
        if (!rules.allChats && (room == null || normalized(room) !in rules.selectedChats.map(::normalized))) return FilterResult(emptyList(), 0, 0, "선택한 채팅방 제목을 확인할 수 없습니다")
        fun dp(value: Int) = (value * density).toInt().coerceAtLeast(1)
        val visible = nodes.withIndex().filter { it.value.visible && it.value.bounds.clip(viewport) != null && !it.value.editable }
        val profiles = visible.filter { (_, n) ->
            val b = n.bounds
            (n.media || n.role.contains("profile") || n.role.contains("avatar")) && b.left - viewport.left in 0..dp(36) && b.width in dp(24)..dp(64) && b.height in dp(16)..dp(70)
        }
        val labels = visible.filter { (_, n) -> n.text.isNotBlank() && n.text.length <= 80 && !n.text.contains('\n') && n.bounds.height <= dp(30) }
        val anchors = mutableListOf<Anchor>()
        for ((_, profile) in profiles) {
            val p = profile.bounds
            val near = labels.filter { (_, n) -> n.bounds.left in p.right..(p.right+dp(48)) && n.bounds.top in (p.top-dp(5))..(p.top+dp(12)) }
            val names = near.map { normalized(it.value.text) }.distinct()
            val fromDescription = Regex("^(.{1,60}?)(?:님의|의) 프로필(?: 사진)?$").matchEntire(profile.description)?.groupValues?.get(1)?.let(::normalized)
            val name = if (names.size == 1) names[0] else if (names.isEmpty()) fromDescription else null
            val header = if (near.size == 1) near[0].value.bounds else Box(p.right+dp(8), p.top, p.right+dp(120), p.top+dp(18))
            anchors += Anchor(p.top, name, header, header.left, p.top < viewport.top || p.bottom > viewport.bottom)
        }
        for ((_, label) in labels) {
            val senderRole = label.role in senderIds || label.role.contains("nick_name") || label.role.contains("nickname") || label.role.endsWith("sender_name")
            if (senderRole && label.bounds.left-viewport.left in dp(36)..dp(180) && anchors.none { kotlin.math.abs(it.y-label.bounds.top) < dp(18) }) {
                anchors += Anchor(label.bounds.top, normalized(label.text), label.bounds, label.bounds.left, label.bounds.top < viewport.top)
            }
        }
        val ordered = anchors.sortedBy { it.y }.distinctBy { it.y / dp(3) }
        val hidden = rules.hiddenUsers.map(::normalized).toSet()
        val mediaParents = mutableSetOf<Int>()
        nodes.forEachIndexed { index, node ->
            if (node.media) {
                var parent = index
                repeat(50) { if (parent in nodes.indices) { mediaParents += parent; parent = nodes[parent].parent } }
            }
        }
        // A readable parent must not turn an outgoing/editable descendant into
        // part of an incoming mask. Hidden templates outside the viewport do not count.
        val protectedAncestors=mutableSetOf<Int>()
        nodes.forEachIndexed { index,node ->
            if (node.visible && (node.outgoing || node.editable) && node.bounds.clip(viewport)!=null) {
                var current=index
                repeat(50) { if (current in nodes.indices) { protectedAncestors+=current;current=nodes[current].parent } }
            }
        }
        fun containerSupports(index: Int, group: Box): Boolean {
            val child=nodes[index]
            var parent=child.parent
            repeat(50) {
                if (parent !in nodes.indices) return false
                val candidate=nodes[parent]
                if (parent in protectedAncestors || (!rules.hideImages && parent in mediaParents)) return false
                if (candidate.visible && candidate.bounds.contains(child.bounds) && candidate.bounds.top>=group.top && candidate.bounds.bottom<=group.bottom && hasContent(candidate)) return true
                parent=candidate.parent
            }
            return false
        }
        val masks = mutableListOf<Box>()
        var matched = 0
        ordered.forEachIndexed { index, anchor ->
            if (anchor.clipped || anchor.name == null || anchor.name !in hidden) return@forEachIndexed
            matched++
            val end = ordered.getOrNull(index+1)?.y?.minus(dp(2)) ?: viewport.bottom
            val start = maxOf(anchor.header.bottom, anchor.y+dp(16), viewport.top)
            if (end <= start) return@forEachIndexed
            val group = Box(viewport.left, start, viewport.right, minOf(end, viewport.bottom))
            visible.forEach { (nodeIndex, node) ->
                val b = node.bounds
                if (node.outgoing || nodeIndex in protectedAncestors || (!rules.hideImages && nodeIndex in mediaParents)) return@forEach
                if (b.width < dp(8) || b.height < dp(10)) return@forEach
                if (b.left !in (anchor.left-dp(12))..(anchor.left+dp(48))) return@forEach
                if (b.top < start-dp(2) || (index+1 < ordered.size && b.bottom > end+dp(2))) return@forEach
                val supported=containerSupports(nodeIndex,group)
                if (timeText.matches(node.text) || countText.matches(node.text)) return@forEach
                if (!hasContent(node) && !node.media && node.role !in messageIds && !supported) return@forEach
                if (!node.leaf && node.role !in messageIds && !hasContent(node) && !supported) return@forEach
                val expanded = Box(b.left-dp(2), b.top-dp(1), b.right+dp(2), b.bottom+dp(1)).clip(group)
                if (expanded != null) masks += expanded
            }
        }
        val deduped = mutableListOf<Box>()
        masks.distinct().sortedByDescending { it.area }.forEach { box -> if (deduped.none { it.contains(box) }) deduped += box }
        val reason = when {
            ordered.isEmpty() -> "카카오톡이 발신자 정보를 제공하지 않거나 채팅 화면이 아닙니다"
            matched == 0 && ordered.any { it.clipped && it.name?.let(hidden::contains) == true } -> "숨김 이름이 보이지만 프로필이 잘려 현재 메시지 소유자를 확정하지 않았습니다"
            matched == 0 -> "읽은 발신자와 숨김 목록에 일치하는 사용자가 없습니다"
            deduped.isEmpty() -> "대상 발신자는 있지만 접근성에서 메시지 영역을 찾지 못했습니다"
            else -> "접근성 정보로 확인한 현재 화면만 처리했습니다"
        }
        return FilterResult(deduped, ordered.count { it.name != null }, matched, reason, ordered.mapNotNull { it.name }.distinct(), ordered.count { it.name == null }, ordered.count { it.clipped })
    }
}
