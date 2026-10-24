package dev.kakaofilter.core

import org.junit.Assert.*
import org.junit.Test

class FilterEngineTest {
    private val viewport=Box(0,100,400,800)
    private val rules=Rules(enabled=true,hiddenUsers=listOf("정민욱"),allChats=true)
    private fun node(box: Box,text: String="",id: String="message_text",media: Boolean=false,outgoing: Boolean=false,editable: Boolean=false,parent: Int=-1,leaf: Boolean=true) = UiNode(box,"com.kakao.talk:id/$id",if (media) "android.widget.ImageView" else "android.widget.TextView",text,parent=parent,leaf=leaf,outgoing=outgoing,editable=editable)
    private fun scene(): List<UiNode> = listOf(
        node(Box(12,120,52,160),id="profile",media=true),
        node(Box(60,120,110,138),"정민욱","nickname"),
        node(Box(60,142,380,180),"긴 메시지"),
        node(Box(60,190,250,330),id="photo",media=true),
        node(Box(60,340,260,370),"연속 메시지"),
        node(Box(12,400,52,440),id="profile",media=true), // Unreadable name still ends ownership.
        node(Box(60,422,300,460),"다른 사람 메시지"),
        node(Box(12,500,52,540),id="profile",media=true),
        node(Box(60,500,110,518),"친구","nickname"),
        node(Box(60,522,300,560),"정민욱") // A name in the body is not a sender.
    )
    @Test fun photoAndConsecutiveMessagesBelongToVisibleSender() {
        val result=FilterEngine.evaluate(scene(),viewport,1f,null,rules)
        assertEquals(1,result.matched);assertEquals(3,result.masks.size)
        assertTrue(result.masks.all { it.bottom<400 })
    }
    @Test fun unknownNextProfileStopsOwnership() {
        val result=FilterEngine.evaluate(scene(),viewport,1f,null,rules)
        assertFalse(result.masks.any { it.top>=400 })
    }
    @Test fun bodyContainingHiddenNameDoesNotIdentifySender() {
        val other=scene().drop(7)
        assertTrue(FilterEngine.evaluate(other,viewport,1f,null,rules).masks.isEmpty())
    }
    @Test fun mediaOptionDoesNotMaskPhoto() {
        val result=FilterEngine.evaluate(scene(),viewport,1f,null,rules.copy(hideImages=false))
        assertEquals(2,result.masks.size)
    }
    @Test fun nearFullWidthBubbleHasNoPercentageLimit() {
        val wide=scene().take(3).map { if (it.text=="긴 메시지") it.copy(bounds=Box(60,142,1834,240)) else it }
        val result=FilterEngine.evaluate(wide,Box(0,100,1917,800),1f,null,rules)
        assertEquals(1,result.masks.size);assertTrue(result.masks[0].right>=1834)
    }
    @Test fun disabledAndWrongRoomDoNotMask() {
        assertTrue(FilterEngine.evaluate(scene(),viewport,1f,null,rules.copy(enabled=false)).masks.isEmpty())
        val selected=rules.copy(allChats=false,selectedChats=listOf("개발방"))
        assertTrue(FilterEngine.evaluate(scene(),viewport,1f,null,selected).masks.isEmpty())
        assertTrue(FilterEngine.evaluate(scene(),viewport,1f,"다른방",selected).masks.isEmpty())
        assertEquals(3,FilterEngine.evaluate(scene(),viewport,1f,"개발방",selected).masks.size)
    }
    @Test fun outgoingAndEditableNodesAreNeverMasked() {
        val first=scene().take(2)
        val nodes=first+node(Box(60,142,380,180),"내 메시지",outgoing=true)+node(Box(60,200,380,240),"입력 중",editable=true)
        assertTrue(FilterEngine.evaluate(nodes,viewport,1f,null,rules).masks.isEmpty())
    }
    @Test fun noVisibleSenderNeverInheritsFromPreviousFrame() {
        FilterEngine.evaluate(scene(),viewport,1f,null,rules)
        assertTrue(FilterEngine.evaluate(listOf(node(Box(60,200,380,240),"이름이 없는 메시지")),viewport,1f,null,rules).masks.isEmpty())
    }
    @Test fun exactNamesOnly() {
        assertTrue(FilterEngine.evaluate(scene(),viewport,1f,null,rules.copy(hiddenUsers=listOf("정민욱2"))).masks.isEmpty())
    }
    @Test fun newScrollCoordinatesAreCalculatedFromCurrentTree() {
        val shifted=scene().map { n -> n.copy(bounds=Box(n.bounds.left,n.bounds.top+30,n.bounds.right,n.bounds.bottom+30)) }
        val first=FilterEngine.evaluate(scene(),viewport,1f,null,rules).masks
        val second=FilterEngine.evaluate(shifted,viewport,1f,null,rules).masks
        assertEquals(first.size,second.size)
        assertEquals(first.map { it.top+30 }.sorted(),second.map { it.top }.sorted())
    }
    @Test fun actualRecognizedNamesAreAvailableForExplicitUserSelection() {
        val result=FilterEngine.evaluate(scene(),viewport,1f,null,rules.copy(hiddenUsers=listOf("입력오타")))
        assertEquals(0,result.matched)
        assertEquals(listOf("정민욱","친구"),result.recognizedNames)
        assertEquals(1,result.unnamedProfiles)
        val selected=rules.copy(hiddenUsers=listOf(result.recognizedNames[0]))
        assertEquals(3,FilterEngine.evaluate(scene(),viewport,1f,null,selected).masks.size)
    }
    @Test fun clippedKnownSenderIsDistinguishedFromANameMismatch() {
        val nodes=listOf(node(Box(12,90,52,130),id="profile",media=true),node(Box(60,95,110,113),"정민욱","nickname"),node(Box(60,135,300,170),"연속 메시지"))
        val result=FilterEngine.evaluate(nodes,viewport,1f,null,rules)
        assertEquals(1,result.senders);assertEquals(0,result.matched);assertEquals(1,result.clippedProfiles)
        assertTrue(result.reason.contains("프로필이 잘려"))
        assertEquals(listOf("정민욱"),result.recognizedNames)
    }
}
