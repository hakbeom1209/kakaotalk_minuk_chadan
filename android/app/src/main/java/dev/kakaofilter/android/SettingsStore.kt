package dev.kakaofilter.android

import android.content.Context
import dev.kakaofilter.core.Rules
import dev.kakaofilter.core.normalized
import org.json.JSONArray
import org.json.JSONObject

class SettingsStore(context: Context) {
    val preferences = context.getSharedPreferences("kakao_filter", Context.MODE_PRIVATE)
    fun load(): Rules = runCatching { decode(preferences.getString("settings", "{}")!!) }.getOrDefault(Rules())
    fun save(rules: Rules) { decode(encode(rules)); check(preferences.edit().putString("settings", encode(rules)).commit()) { "설정 저장 실패" } }
    companion object {
        fun decode(text: String): Rules {
            require(text.toByteArray().size <= 65536) { "설정 파일은 64KB 이하여야 합니다" }
            val json = JSONObject(text)
            require(!(json.has("schema") && json.has("nodes"))) { "진단 파일은 설정 파일로 가져올 수 없습니다" }
            fun list(key: String): List<String> {
                val array = json.optJSONArray(key) ?: if (json.has(key)) error("$key: 문자열 목록이 필요합니다") else JSONArray()
                require(array.length() <= 200) { "$key: 최대 200개" }
                return (0 until array.length()).map {
                    val value = array.get(it)
                    require(value is String && value.length <= 200) { "$key: 유효하지 않은 이름" }
                    normalized(value)
                }.filter { it.isNotBlank() }.distinct()
            }
            fun boolean(key: String, fallback: Boolean): Boolean {
                if (!json.has(key)) return fallback
                return (json.get(key) as? Boolean) ?: error("$key: 참/거짓 값이 필요합니다")
            }
            val scope = json.optString("chatScope", "selected")
            require(scope in setOf("all", "selected")) { "chatScope 값이 올바르지 않습니다" }
            val mode = json.optString("displayMode", "opaque")
            require(mode in setOf("opaque", "placeholder", "blur")) { "displayMode 값이 올바르지 않습니다" }
            return Rules(boolean("enabled", false), list("hiddenUsers"), list("selectedChats"), scope == "all", boolean("hideImages", true), if (mode == "blur") "opaque" else mode)
        }
        fun encode(rules: Rules) = JSONObject().apply {
            put("enabled", rules.enabled); put("hiddenUsers", JSONArray(rules.hiddenUsers))
            put("selectedChats", JSONArray(rules.selectedChats)); put("chatScope", if (rules.allChats) "all" else "selected")
            put("hideImages", rules.hideImages); put("displayMode", rules.displayMode); put("autoStart", false)
        }.toString(2)
    }
}
