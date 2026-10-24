package dev.kakaofilter.core

import org.junit.Assert.*
import org.junit.Test

class VisualFilterSessionTest {
    private val viewport=Box(0,100,400,700)
    private val rules=Rules(true,listOf("대상"),allChats=true,rememberMessages=true)
    private val sender=listOf(UiNode(Box(12,120,52,160),id="profile",className="android.widget.ImageView"),UiNode(Box(60,120,130,138),id="nickname",text="대상"))
    private val bubbles=listOf(ReadBubble(Box(60,150,350,200),true,"first"),ReadBubble(Box(60,215,260,275),true,"second"),ReadBubble(Box(170,300,390,350),false,"reply"))
    @Test fun missingConsecutiveAccessibilityNodesAndScrolledOffSenderAreHandledTogether() {
        val session=VisualFilterSession()
        val first=session.evaluate("room",sender,viewport,1f,null,rules,bubbles)
        assertEquals(2,first.filter.masks.size)
        val moved=bubbles.map { it.copy(bounds=Box(it.bounds.left,it.bounds.top-30,it.bounds.right,it.bounds.bottom-30)) }
        val again=session.evaluate("room",emptyList(),viewport,1f,null,rules,moved)
        assertEquals(0,again.filter.matched)
        assertEquals(2,again.reused)
        assertEquals(listOf(118,183),again.filter.masks.map { it.top }.sorted())
    }
    @Test fun anotherVisibleSenderCannotBorrowRememberedMasks() {
        val session=VisualFilterSession()
        session.evaluate("room",sender,viewport,1f,null,rules,bubbles)
        val other=sender.map { if (it.text=="대상") it.copy(text="친구") else it }
        assertTrue(session.evaluate("room",other,viewport,1f,null,rules,bubbles).filter.masks.isEmpty())
    }
    @Test fun cachedMessagesNeverBypassDisabledFilterRoomOrChangedHiddenNames() {
        val session=VisualFilterSession()
        session.evaluate("room",sender,viewport,1f,null,rules,bubbles)
        assertTrue(session.evaluate("room",emptyList(),viewport,1f,null,rules.copy(enabled=false),bubbles).filter.masks.isEmpty())
        session.evaluate("room",sender,viewport,1f,null,rules,bubbles)
        assertTrue(session.evaluate("room",emptyList(),viewport,1f,null,rules.copy(hiddenUsers=listOf("다른 이름")),bubbles).filter.masks.isEmpty())
        session.evaluate("room",sender,viewport,1f,null,rules,bubbles)
        assertTrue(session.evaluate("room",emptyList(),viewport,1f,null,rules.copy(allChats=false,selectedChats=listOf("선택한 방")),bubbles).filter.masks.isEmpty())
    }
    @Test fun mediaExcludedAndOutgoingDescendantsAreStillProtected() {
        val session=VisualFilterSession()
        val nodes=sender+UiNode(bubbles[1].bounds,className="android.widget.ImageView")+UiNode(bubbles[0].bounds,text="내가 보낸 글",outgoing=true)
        assertTrue(session.evaluate("room",nodes,viewport,1f,null,rules.copy(hideImages=false),bubbles).filter.masks.isEmpty())
    }
}
