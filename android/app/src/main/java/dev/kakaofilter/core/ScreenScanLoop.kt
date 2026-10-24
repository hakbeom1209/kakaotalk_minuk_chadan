package dev.kakaofilter.core

enum class ScanState { KAKAO, UNAVAILABLE, INACTIVE }

/** Re-read settling lists even when Android sends no final content event. */
class ScreenScanLoop(
    private val now: () -> Long,
    private val post: (Runnable, Long) -> Unit,
    private val cancel: (Runnable) -> Unit,
    private val scan: () -> ScanState
) {
    private var due: Long? = null
    private var lastActive: Long? = null
    private var lastEvent: Long? = null
    private val tick = Runnable { refresh() }

    fun request(kakaoEvent: Boolean = false) {
        if (kakaoEvent) { lastEvent=now(); lastActive=now() }
        enqueue(24)
    }

    fun stop() {
        cancel(tick); due=null; lastActive=null; lastEvent=null
    }

    private fun enqueue(delay: Long) {
        val next=now()+delay
        if (due?.let { it<=next } == true) return
        cancel(tick)
        due=next
        post(tick,delay)
    }

    private fun refresh() {
        due=null
        when (scan()) {
            ScanState.KAKAO -> {
                lastActive=now()
                enqueue(if (lastEvent?.let { now()-it<1500 } == true) 100 else 400)
            }
            ScanState.UNAVAILABLE -> {
                // A transient missing root must not require another user action,
                // but never poll indefinitely once the foreground is unknown.
                if (lastActive?.let { now()-it<1500 } == true) enqueue(100)
                else { lastActive=null; lastEvent=null }
            }
            ScanState.INACTIVE -> { lastActive=null; lastEvent=null }
        }
    }
}
