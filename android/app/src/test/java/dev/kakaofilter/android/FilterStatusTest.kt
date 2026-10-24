package dev.kakaofilter.android

import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class FilterStatusTest {
    @Before fun reset() { FilterStatus.listeners.clear();FilterStatus.namesVisible(false);FilterStatus.settingsChanged() }
    @Test fun returningToSettingsDoesNotEraseLastKakaoObservation() {
        FilterStatus.namesVisible(true)
        FilterStatus.result("발신자 2 · 대상 0 · 가림막 0",listOf("정민욱","친구"))
        FilterStatus.update("현재 다른 앱/설정 화면 · 가림막 일시 중지")
        assertTrue(FilterStatus.lastResult.contains("발신자 2"))
        assertEquals(listOf("정민욱","친구"),FilterStatus.lastNames)
    }
    @Test fun namesRequireOptInAndAreClearedWhenTurnedOff() {
        FilterStatus.result("counts",listOf("정민욱"))
        assertTrue(FilterStatus.lastNames.isEmpty())
        FilterStatus.namesVisible(true);FilterStatus.result("counts",listOf("정민욱"))
        assertEquals(listOf("정민욱"),FilterStatus.lastNames)
        FilterStatus.namesVisible(false)
        assertTrue(FilterStatus.lastNames.isEmpty())
    }
}
