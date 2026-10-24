package dev.kakaofilter.core

import org.junit.Assert.*
import org.junit.Test

class ScreenScanLoopTest {
    private class Clock {
        var time=0L
        var state=ScanState.KAKAO
        val reads=mutableListOf<Long>()
        val pending=mutableMapOf<Runnable,Long>()
        val loop=ScreenScanLoop({ time },{ task,delay -> pending[task]=time+delay },{ pending.remove(it) }) { reads+=time; state }
        fun advance(until: Long) {
            while (pending.values.any { it<=until }) {
                val task=pending.minBy { it.value }
                time=task.value; pending.remove(task.key); task.key.run()
            }
            time=until
        }
    }

    @Test fun scrollIsRecheckedWithoutAFinalAccessibilityEvent() {
        val clock=Clock()
        clock.loop.request(kakaoEvent=true)
        clock.advance(325)
        assertEquals(listOf(24L,124L,224L,324L),clock.reads)
        assertEquals(1,clock.pending.size)
    }

    @Test fun newScrollExpeditesAnIdleRefreshWithoutDuplicatingIt() {
        val clock=Clock()
        clock.loop.request(); clock.advance(24)
        assertEquals(listOf(424L),clock.pending.values.toList())
        clock.advance(40); clock.loop.request(kakaoEvent=true)
        clock.advance(41); clock.loop.request(kakaoEvent=true)
        clock.advance(64)
        assertEquals(listOf(24L,64L),clock.reads)
        assertEquals(1,clock.pending.size)
    }

    @Test fun missingRootDuringScrollRecoversWithoutAnotherEvent() {
        val clock=Clock()
        clock.state=ScanState.UNAVAILABLE
        clock.loop.request(kakaoEvent=true); clock.advance(124)
        clock.state=ScanState.KAKAO; clock.advance(224)
        assertEquals(listOf(24L,124L,224L),clock.reads)
        assertEquals(1,clock.pending.size)
    }

    @Test fun missingForegroundRetriesAreBounded() {
        val clock=Clock()
        clock.state=ScanState.UNAVAILABLE
        clock.loop.request(kakaoEvent=true); clock.advance(5000)
        assertTrue(clock.reads.size in 2..17)
        assertTrue(clock.pending.isEmpty())
    }

    @Test fun leavingKakaoAndStoppingBothCancelFurtherReads() {
        val clock=Clock()
        clock.loop.request(kakaoEvent=true); clock.advance(24)
        clock.state=ScanState.INACTIVE; clock.advance(1000)
        assertEquals(listOf(24L,124L),clock.reads)
        assertTrue(clock.pending.isEmpty())
        clock.state=ScanState.KAKAO; clock.loop.request(kakaoEvent=true)
        clock.loop.stop(); clock.advance(2000)
        assertEquals(2,clock.reads.size)
        assertTrue(clock.pending.isEmpty())
    }

    @Test fun settledForegroundUsesASlowerRefresh() {
        val clock=Clock()
        clock.loop.request(kakaoEvent=true); clock.advance(2000)
        assertTrue(clock.pending.values.single()-clock.reads.last()==400L)
    }
}
