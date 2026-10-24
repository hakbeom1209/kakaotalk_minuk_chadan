package dev.kakaofilter.core

import org.junit.Assert.*
import org.junit.Test

class MessageMemoryTest {
    private fun bubble(key: String,y: Int,owner: MessageOwner=MessageOwner.UNKNOWN)=RememberedBubble(Box(60,y,280,y+40),key,owner)
    @Test fun confirmedMessagesAreRememberedAtNewPositionsWithoutSenderRedetection() {
        val memory=MessageMemory()
        val first=listOf(bubble("first",200,MessageOwner.HIDDEN),bubble("second",250,MessageOwner.HIDDEN),bubble("reply",320,MessageOwner.OTHER))
        assertEquals(2,memory.apply("chat",first).masks.size)
        val scrolled=first.map { it.copy(bounds=Box(it.bounds.left,it.bounds.top-100,it.bounds.right,it.bounds.bottom-100),owner=MessageOwner.UNKNOWN) }
        val result=memory.apply("chat",scrolled)
        assertEquals(2,result.reused)
        assertEquals(listOf(100,150),result.masks.map { it.top })
        // Scrolling away does not delete the remembered identities.
        memory.apply("chat",emptyList())
        assertEquals(2,memory.apply("chat",scrolled).reused)
    }
    @Test fun identicalBodyFromAnotherSenderOverridesMemory() {
        val memory=MessageMemory()
        memory.apply("chat",listOf(bubble("yes",200,MessageOwner.HIDDEN),bubble("next",250)))
        assertTrue(memory.apply("chat",listOf(bubble("yes",200,MessageOwner.OTHER),bubble("next",250))).masks.isEmpty())
        assertTrue(memory.apply("chat",listOf(bubble("yes",200),bubble("next",250))).masks.isEmpty())
    }
    @Test fun aBodyAloneOrDifferentContextDoesNotIdentifyAnUnknownSender() {
        val memory=MessageMemory()
        memory.apply("chat",listOf(bubble("yes",200,MessageOwner.HIDDEN),bubble("original neighbor",250)))
        assertTrue(memory.apply("chat",listOf(bubble("yes",200))).masks.isEmpty())
        assertTrue(memory.apply("chat",listOf(bubble("yes",200),bubble("different neighbor",250))).masks.isEmpty())
        assertTrue(memory.apply("chat",listOf(bubble("changed body",200),bubble("original neighbor",250))).masks.isEmpty())
    }
    @Test fun duplicateBubblesAndOtherRoomsDoNotBorrowOwnership() {
        val memory=MessageMemory()
        memory.apply("chat",listOf(bubble("first",200,MessageOwner.HIDDEN),bubble("second",250,MessageOwner.HIDDEN)))
        assertTrue(memory.apply("chat",listOf(bubble("first",120),bubble("second",170),bubble("first",220),bubble("second",270))).masks.isEmpty())
        assertTrue(memory.apply("other chat",listOf(bubble("first",200),bubble("second",250))).masks.isEmpty())
    }
    @Test fun explicitClearAndCapacityBoundMemory() {
        val memory=MessageMemory(2)
        val result=memory.apply("chat",(0..10).map { bubble("$it",100+it*50,MessageOwner.HIDDEN) })
        assertEquals(2,result.remembered)
        memory.clear()
        assertTrue(memory.apply("chat",listOf(bubble("9",200),bubble("10",250))).masks.isEmpty())
    }
    @Test fun measuredScrollMovesMasksAndRestoresPartiallyClippedEdges() {
        val tracker=ScrollingMasks()
        val viewport=Box(0,100,400,800)
        tracker.replace(listOf(Box(60,120,280,180)),viewport,3)
        assertEquals(listOf(Box(60,100,280,130)),tracker.scroll(3,50))
        assertEquals(listOf(Box(60,120,280,180)),tracker.scroll(3,-50))
        assertNull(tracker.scroll(4,50));assertTrue(tracker.boxes.isEmpty())
    }
    @Test fun unknownScrollDeltaNeverLeavesFixedOldCoordinates() {
        val tracker=ScrollingMasks()
        tracker.replace(listOf(Box(60,120,280,180)),Box(0,100,400,800),3)
        assertNull(tracker.scroll(3,0));assertTrue(tracker.boxes.isEmpty())
    }
    @Test fun partiallyOffscreenBubbleRequiresTranslatedBoundsAndExactVisibleTextRows() {
        val memory=MessageMemory()
        val rows=(1L..40L).toList()
        val full=bubble("full",200,MessageOwner.HIDDEN).copy(rows=rows)
        memory.apply("chat",listOf(full))
        val partial=bubble("partial",100).copy(rows=rows.takeLast(20),clippedTop=true,tracked=true)
        assertEquals(1,memory.apply("chat",listOf(partial)).reused)
        assertTrue(memory.apply("chat",listOf(partial.copy(tracked=false))).masks.isEmpty())
        assertTrue(memory.apply("chat",listOf(partial.copy(rows=(100L..119L).toList()))).masks.isEmpty())
        assertTrue(memory.apply("chat",listOf(partial.copy(owner=MessageOwner.OTHER))).masks.isEmpty())
    }
    @Test fun unchangedSingleBubbleStaysMaskedWithoutRequiringAVisibleSender() {
        val memory=MessageMemory()
        memory.apply("chat",listOf(bubble("full",200,MessageOwner.HIDDEN)))
        assertEquals(1,memory.apply("chat",listOf(bubble("full",120).copy(tracked=true))).reused)
        assertTrue(memory.apply("chat",listOf(bubble("recycled different message",120).copy(tracked=true))).masks.isEmpty())
    }
}
