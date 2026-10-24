package dev.kakaofilter.android

import dev.kakaofilter.core.Rules
import org.junit.Assert.*
import org.junit.Test

class SettingsTest {
    @Test fun sharedSettingsRoundTrip() {
        val rules=Rules(true,listOf("정민욱"),listOf("개발방"),false,true,"placeholder")
        assertEquals(rules,SettingsStore.decode(SettingsStore.encode(rules)))
    }
    @Test fun pcFieldsAreAcceptedAndBlurBecomesOpaque() {
        val rules=SettingsStore.decode("""{"enabled":true,"hiddenUsers":[" 정민욱 ","정민욱"],"chatScope":"all","displayMode":"blur","autoStart":true,"topMargin":75}""")
        assertTrue(rules.allChats);assertEquals(listOf("정민욱"),rules.hiddenUsers);assertEquals("opaque",rules.displayMode)
    }
    @Test fun invalidTypesAreRejected() {
        for (json in listOf("""{"enabled":"true"}""","""{"hiddenUsers":"정민욱"}""","""{"hiddenUsers":[7]}""","""{"chatScope":"wrong"}""")) {
            assertThrows(RuntimeException::class.java) { SettingsStore.decode(json) }
        }
    }
    @Test fun oversizedInputIsRejectedBeforeParsing() {
        assertThrows(IllegalArgumentException::class.java) { SettingsStore.decode(" ".repeat(65537)) }
    }
    @Test fun missingSettingsStartDisabled() { assertFalse(SettingsStore.decode("{}").enabled) }
    @Test fun screenAnalysisRequiresExplicitOptInAndRoundTrips() {
        assertFalse(SettingsStore.decode("{}").rememberMessages)
        val rules=Rules(rememberMessages=true)
        assertEquals(rules,SettingsStore.decode(SettingsStore.encode(rules)))
        assertThrows(RuntimeException::class.java) { SettingsStore.decode("""{"rememberMessages":"true"}""") }
    }
}
