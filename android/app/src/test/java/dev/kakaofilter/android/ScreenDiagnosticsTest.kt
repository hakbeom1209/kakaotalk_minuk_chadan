package dev.kakaofilter.android

import dev.kakaofilter.core.Box
import dev.kakaofilter.core.FilterResult
import dev.kakaofilter.core.Rules
import dev.kakaofilter.core.UiNode
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ScreenDiagnosticsTest {
    @Test fun exportedStructureExcludesNamesMessagesDescriptionsAndRoomTitles() {
        val secret="개인 대화 내용 비밀"
        val nickname="아주특별한별명"
        val room="개인용 채팅방"
        val nodes=listOf(UiNode(Box(60,120,120,140),id="com.kakao.talk:id/nickname",text=nickname,description=secret),UiNode(Box(60,145,300,180),text=secret,parent=0))
        val text=ScreenDiagnostics.create(nodes,Rules(true,listOf(nickname),listOf(room)),3f,36,"test",true,false,"layout diagnosis")
        assertFalse(text.contains(secret));assertFalse(text.contains(nickname));assertFalse(text.contains(room))
        val json=JSONObject(text)
        assertEquals(2,json.getInt("nodeCount"))
        val first=json.getJSONArray("nodes").getJSONObject(0)
        assertEquals("com.kakao.talk:id/nickname",first.getString("id"))
        assertTrue(first.getBoolean("matchesConfiguredName"))
        assertFalse(first.has("text"));assertFalse(first.has("description"))
    }
    @Test fun missingInputAndTruncationAreDiagnosableWithoutText() {
        val data=JSONObject(ScreenDiagnostics.create(emptyList(),Rules(),2f,36,"test",false,true,"incomplete"))
        assertFalse(data.getBoolean("conversationDetected"));assertTrue(data.getBoolean("truncated"))
        assertEquals(0,data.getInt("editableCount"))
    }
    @Test fun diagnosticIsNotAcceptedAsSettings() {
        val data=ScreenDiagnostics.create(emptyList(),Rules(),2f,36,"test",false,false,"none")
        assertThrows(IllegalArgumentException::class.java) { SettingsStore.decode(data) }
    }
    @Test fun viewportMaskGeometryAndNonContentLabelsHelpLocateSkippedBubbles() {
        val nodes=listOf(UiNode(Box(60,150,200,190),text="연속 메시지"),UiNode(Box(210,175,240,190),text="오전 1:31"),UiNode(Box(205,155,220,170),text="5"))
        val viewport=Box(0,100,400,800)
        val mask=Box(58,149,202,191)
        val text=ScreenDiagnostics.create(nodes,Rules(),1f,36,"test",true,false,"result",viewport,FilterResult(listOf(mask),2,1,"result"))
        val json=JSONObject(text)
        assertEquals("[0,100,400,800]",json.getJSONArray("viewport").toString())
        assertEquals("[58,149,202,191]",json.getJSONArray("masks").getJSONArray(0).toString())
        assertEquals(1,json.getInt("matchedCount"))
        assertTrue(json.getJSONArray("nodes").getJSONObject(1).getBoolean("textIsTime"))
        assertTrue(json.getJSONArray("nodes").getJSONObject(2).getBoolean("textIsCounter"))
        assertFalse(text.contains("연속 메시지"));assertFalse(text.contains("오전 1:31"))
    }
}
