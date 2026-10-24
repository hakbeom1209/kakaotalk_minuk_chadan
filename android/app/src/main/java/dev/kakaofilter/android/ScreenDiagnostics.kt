package dev.kakaofilter.android

import dev.kakaofilter.core.Box
import dev.kakaofilter.core.Rules
import dev.kakaofilter.core.UiNode
import dev.kakaofilter.core.normalized
import org.json.JSONArray
import org.json.JSONObject

/** Explicit, one-shot structural diagnosis. Neither text nor descriptions are exported. */
object ScreenDiagnostics {
    private fun bounds(box: Box) = JSONArray(listOf(box.left,box.top,box.right,box.bottom))
    fun create(nodes: List<UiNode>, rules: Rules, density: Float, androidSdk: Int, appVersion: String,
               conversation: Boolean, truncated: Boolean, reason: String): String {
        val hidden=rules.hiddenUsers.map(::normalized).toSet()
        val items=JSONArray()
        nodes.forEachIndexed { index,node ->
            items.put(JSONObject().apply {
                put("index",index); put("parent",node.parent); put("id",node.id); put("class",node.className)
                put("bounds",bounds(node.bounds)); put("visible",node.visible); put("editable",node.editable)
                put("outgoing",node.outgoing); put("leaf",node.leaf); put("scrollable",node.scrollable)
                put("textLength",node.text.length); put("descriptionLength",node.description.length)
                put("matchesConfiguredName",node.text.isNotBlank() && normalized(node.text) in hidden)
            })
        }
        return JSONObject().apply {
            put("schema",1); put("appVersion",appVersion); put("androidSdk",androidSdk); put("density",density)
            put("nodeCount",nodes.size); put("conversationDetected",conversation); put("truncated",truncated)
            put("filterEnabled",rules.enabled); put("hiddenUserCount",rules.hiddenUsers.size)
            put("allChats",rules.allChats); put("selectedChatCount",rules.selectedChats.size)
            put("editableCount",nodes.count { it.visible && it.editable }); put("reason",reason)
            put("nodes",items)
        }.toString(2)
    }
}
