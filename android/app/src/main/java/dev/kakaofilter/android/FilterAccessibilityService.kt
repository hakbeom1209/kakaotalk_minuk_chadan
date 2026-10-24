package dev.kakaofilter.android

import android.accessibilityservice.AccessibilityService
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.content.res.Configuration
import android.graphics.Rect
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import dev.kakaofilter.core.Box
import dev.kakaofilter.core.FilterEngine
import dev.kakaofilter.core.UiNode
import java.lang.ref.WeakReference

object FilterStatus {
    var message = "접근성 서비스를 켜주세요"; private set
    var lastResult = ""; private set
    fun result(value: String) { lastResult = value; update(value) }
    var service: WeakReference<FilterAccessibilityService>? = null
    val listeners = mutableSetOf<() -> Unit>()
    fun update(value: String) { if (message == value) return; message = value; listeners.toList().forEach { it() } }
}

class FilterAccessibilityService : AccessibilityService() {
    private lateinit var store: SettingsStore
    private lateinit var overlay: MaskOverlay
    private val handler = Handler(Looper.getMainLooper())
    private var scheduled = false
    private var testing = false
    private var receiverRegistered = false
    private val scanner = Runnable { scheduled = false; scan() }
    private val endTest = Runnable { testing = false; overlay.clear(); schedule() }
    private val changed = SharedPreferences.OnSharedPreferenceChangeListener { _, _ -> testing = false; handler.removeCallbacks(endTest); overlay.clear(); schedule() }
    private val screen = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            testing = false; overlay.clear(); handler.removeCallbacks(scanner); handler.removeCallbacks(endTest); scheduled = false
            FilterStatus.update("화면 꺼짐 · 가림막 제거")
        }
    }
    override fun onServiceConnected() {
        store = SettingsStore(this)
        if (::overlay.isInitialized) overlay.destroy()
        overlay = MaskOverlay(this)
        store.preferences.registerOnSharedPreferenceChangeListener(changed)
        if (!receiverRegistered) {
            if (Build.VERSION.SDK_INT >= 33) registerReceiver(screen, IntentFilter(Intent.ACTION_SCREEN_OFF), RECEIVER_NOT_EXPORTED)
            else registerReceiver(screen, IntentFilter(Intent.ACTION_SCREEN_OFF))
            receiverRegistered = true
        }
        FilterStatus.service = WeakReference(this)
        FilterStatus.update("연결됨 · 설정 저장 후 카카오톡 채팅방을 여세요")
        schedule()
    }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (!::overlay.isInitialized || testing) return
        // Ignore our status-label content updates to avoid an accessibility feedback loop.
        if (event?.packageName?.toString() == packageName && event.eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) return
        // Any layout/content event can move messages. Clear stale masks before the next pass.
        overlay.clear()
        schedule()
    }
    private fun schedule() {
        if (!scheduled && !testing) { scheduled = true; handler.postDelayed(scanner, 24) }
    }
    private fun scan() {
        if (!::store.isInitialized || testing) return
        val power = getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val keyguard = getSystemService(Context.KEYGUARD_SERVICE) as android.app.KeyguardManager
        if (!power.isInteractive || keyguard.isKeyguardLocked) { overlay.clear(); FilterStatus.update("화면 꺼짐/잠금 · 가림막 제거"); return }
        val rules = store.load()
        if (!rules.enabled) { overlay.clear(); FilterStatus.update("필터 꺼짐"); return }
        val root = rootInActiveWindow
        if (root == null) { overlay.clear(); FilterStatus.update("전면 창을 확인할 수 없습니다"); return }
        try {
            if (root.packageName?.toString() != "com.kakao.talk") { overlay.clear(); FilterStatus.update("대기 · 카카오톡이 전면에 없습니다"); return }
            val nodes = mutableListOf<UiNode>()
            var truncated = false
            fun visit(node: AccessibilityNodeInfo, parent: Int, depth: Int, inheritedEditable: Boolean, inheritedOutgoing: Boolean) {
                if (nodes.size >= 3000 || depth > 50) { truncated = true; return }
                val r = Rect(); node.getBoundsInScreen(r)
                val id = node.viewIdResourceName.orEmpty()
                val className = node.className?.toString().orEmpty()
                val editable = inheritedEditable || node.isEditable || className.endsWith("EditText")
                val outgoing = inheritedOutgoing || listOf("outgoing", "right_message", "my_message", "sending_message").any { id.contains(it, true) }
                val index = nodes.size
                val count = node.childCount
                nodes += UiNode(Box(r.left,r.top,r.right,r.bottom), id, className, if (editable) "" else node.text?.toString().orEmpty(), if (editable) "" else node.contentDescription?.toString().orEmpty(), parent, count == 0, editable, outgoing, node.isScrollable, node.isVisibleToUser)
                for (i in 0 until count) {
                    val child = node.getChild(i) ?: continue
                    try { visit(child, index, depth+1, editable, outgoing) }
                    finally { @Suppress("DEPRECATION") child.recycle() }
                }
            }
            visit(root,-1,0,false,false)
            if (truncated || nodes.isEmpty()) { overlay.clear(); FilterStatus.update("화면 구조가 너무 크거나 불완전해 가리지 않았습니다"); return }
            val density = resources.displayMetrics.density
            val rootBox = nodes[0].bounds
            val conversation = nodes.any { it.visible && it.editable && it.bounds.top > rootBox.top+rootBox.height*.55 && it.bounds.width > rootBox.width*.3 }
            if (!conversation) { overlay.clear(); FilterStatus.update("대기 · 채팅 입력창이 보이는 대화방에서만 작동합니다"); return }
            val viewport = nodes.filter { !it.editable && (it.scrollable || it.className.endsWith("RecyclerView") || it.className.endsWith("ListView")) && it.bounds.width >= rootBox.width*.7 && it.bounds.height >= 120*density }
                .maxByOrNull { it.bounds.area }?.bounds?.clip(rootBox)
                ?: Box(rootBox.left,rootBox.top+(96*density).toInt(),rootBox.right,rootBox.bottom-(80*density).toInt())
            val titleIds = setOf("title","toolbar_title","chat_title","chat_room_title","room_title","action_bar_title","title_text","title_view","chatroom_name","chat_name")
            val titles = nodes.filter { it.role in titleIds && it.bounds.top < viewport.top && it.text.isNotBlank() }.map { it.text }.distinct()
            val room = titles.singleOrNull()
            val result = FilterEngine.evaluate(nodes,viewport,density,room,rules)
            // A new application may have become active while Android supplied nodes.
            val current = rootInActiveWindow
            val stillCurrent = try { current?.packageName?.toString() == "com.kakao.talk" && current.windowId == root.windowId }
                finally { @Suppress("DEPRECATION") current?.recycle() }
            if (!stillCurrent) { overlay.clear(); return }
            overlay.show(result.masks,rules.displayMode)
            FilterStatus.result("발신자 ${result.senders} · 대상 ${result.matched} · 가림막 ${result.masks.size}\n${result.reason}")
        } catch (error: Exception) {
            overlay.clear()
            FilterStatus.update("화면 읽기/가림막 오류 (${error.javaClass.simpleName}) · 권한과 카카오톡 버전을 확인하세요")
        } finally { @Suppress("DEPRECATION") root.recycle() }
    }
    fun testOverlay() {
        if (!::overlay.isInitialized) return
        testing = true
        handler.removeCallbacks(scanner); scheduled = false
        val dm = resources.displayMetrics
        try {
            overlay.show(listOf(Box((dm.widthPixels*.15f).toInt(),(dm.heightPixels*.3f).toInt(),(dm.widthPixels*.85f).toInt(),(dm.heightPixels*.3f+72*dm.density).toInt())),"placeholder")
            FilterStatus.update("테스트 가림막 표시 · 5초 후 제거")
            handler.removeCallbacks(endTest)
            handler.postDelayed(endTest,5000)
        } catch (error: Exception) {
            testing=false; overlay.clear()
            FilterStatus.update("테스트 가림막 표시 실패 (${error.javaClass.simpleName}) · 접근성 권한을 확인하세요")
        }
    }
    override fun onConfigurationChanged(newConfig: Configuration) { super.onConfigurationChanged(newConfig); if (::overlay.isInitialized) { overlay.clear(); schedule() } }
    override fun onInterrupt() { testing=false; handler.removeCallbacks(scanner); handler.removeCallbacks(endTest); scheduled=false; if (::overlay.isInitialized) overlay.clear(); FilterStatus.update("접근성 서비스 일시 중단") }
    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        if (::store.isInitialized) store.preferences.unregisterOnSharedPreferenceChangeListener(changed)
        if (::overlay.isInitialized) overlay.destroy()
        if (receiverRegistered) unregisterReceiver(screen)
        FilterStatus.service = null
        FilterStatus.update("접근성 서비스 꺼짐")
        super.onDestroy()
    }
}
