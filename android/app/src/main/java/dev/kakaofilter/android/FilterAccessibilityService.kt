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
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import dev.kakaofilter.core.Box
import dev.kakaofilter.core.FilterEngine
import dev.kakaofilter.core.UiNode
import dev.kakaofilter.core.ScanState
import dev.kakaofilter.core.ScreenScanLoop
import dev.kakaofilter.core.ScrollingMasks
import dev.kakaofilter.core.VisualFilterSession
import dev.kakaofilter.core.FilterResult
import dev.kakaofilter.core.Rules
import java.security.MessageDigest
import java.lang.ref.WeakReference

object FilterStatus {
    var message = "접근성 서비스를 켜주세요"; private set
    var lastResult = ""; private set
    var lastNames = emptyList<String>(); private set
    var showNames = false; private set
    var diagnostics = ""; private set
    var diagnosticPending = false; private set
    var service: WeakReference<FilterAccessibilityService>? = null
    val listeners = mutableSetOf<() -> Unit>()
    private fun notifyChanged() { listeners.toList().forEach { it() } }
    fun update(value: String) { if (message == value) return; message=value; notifyChanged() }
    fun result(value: String, names: List<String> = emptyList()) {
        val visibleNames=if (showNames) names.toList() else emptyList()
        if (lastResult==value && message==value && lastNames==visibleNames) return
        lastResult=value
        lastNames=visibleNames
        message=value
        notifyChanged()
    }
    fun settingsChanged() { lastResult=""; lastNames=emptyList(); diagnostics=""; diagnosticPending=false; update("설정 저장됨 · 카카오톡 채팅방을 열면 새 설정을 적용합니다") }
    fun namesVisible(value: Boolean) { showNames=value; if (!value) lastNames=emptyList(); notifyChanged() }
    fun requestDiagnostics() { diagnostics=""; diagnosticPending=true; update("진단 대기 · 카카오톡 채팅방을 열고 돌아오세요") }
    fun saveDiagnostics(value: String) { diagnostics=value; diagnosticPending=false; notifyChanged() }
}

class FilterAccessibilityService : AccessibilityService() {
    private lateinit var store: SettingsStore
    private lateinit var overlay: MaskOverlay
    private val handler = Handler(Looper.getMainLooper())
    private var testing = false
    private var receiverRegistered = false
    private val scrollingMasks=ScrollingMasks()
    private val visualSession=VisualFilterSession()
    private var windowReader: WindowBubbleReader?=null
    private var revision=0L
    private var navigation=0L
    private var captureBusy=false
    private var lastCaptureAt=-1000L
    private var chatIdentity: String?=null
    private val scans = ScreenScanLoop({ SystemClock.uptimeMillis() },
        { task,delay -> handler.postDelayed(task,delay); Unit },
        { handler.removeCallbacks(it) },{ scan() })
    private val endTest = Runnable { testing = false; overlay.clear(); schedule() }
    private val changed = SharedPreferences.OnSharedPreferenceChangeListener { _, _ -> testing = false; handler.removeCallbacks(endTest); clearGeometry(); visualSession.clear();chatIdentity=null; FilterStatus.settingsChanged(); schedule() }
    private val screen = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            testing = false; clearGeometry();navigation++; scans.stop(); handler.removeCallbacks(endTest)
            FilterStatus.update("화면 꺼짐 · 가림막 제거")
        }
    }
    override fun onServiceConnected() {
        serviceInfo?.let { info ->
            info.flags = info.flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or android.accessibilityservice.AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
            serviceInfo=info
        }
        store = SettingsStore(this)
        if (::overlay.isInitialized) overlay.destroy()
        overlay = MaskOverlay(this)
        if (Build.VERSION.SDK_INT>=34) { windowReader?.close();windowReader=WindowBubbleReader(this) }
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
        revision++
        val kakao=event?.packageName?.toString()=="com.kakao.talk"
        val remembering=::store.isInitialized && store.load().let { it.enabled && it.rememberMessages } && Build.VERSION.SDK_INT>=34
        if (event?.eventType==AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) navigation++
        if (remembering && kakao && event?.eventType==AccessibilityEvent.TYPE_VIEW_SCROLLED) {
            val shifted=scrollingMasks.scroll(event.windowId,event.scrollDeltaY)
            if (shifted==null) clearGeometry() else overlay.show(shifted,store.load().displayMode)
        } else if (!remembering || !kakao || event?.eventType!=AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) clearGeometry()
        scans.request(kakaoEvent=kakao)
    }
    private fun clearGeometry() { revision++;scrollingMasks.clear();if (::overlay.isInitialized) overlay.clear() }
    private fun showMasks(boxes: List<Box>, viewport: Box, window: Int, mode: String) {
        scrollingMasks.replace(boxes,viewport,window)
        overlay.show(scrollingMasks.boxes,mode)
    }
    private fun schedule() {
        if (!testing) scans.request()
    }
    private fun scan(): ScanState {
        if (!::store.isInitialized || testing) return ScanState.INACTIVE
        val power = getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val keyguard = getSystemService(Context.KEYGUARD_SERVICE) as android.app.KeyguardManager
        if (!power.isInteractive || keyguard.isKeyguardLocked) { clearGeometry(); FilterStatus.update("화면 꺼짐/잠금 · 가림막 제거"); return ScanState.INACTIVE }
        val rules = store.load()
        if (!rules.enabled && !FilterStatus.diagnosticPending) { clearGeometry();visualSession.clear(); FilterStatus.update("필터 저장 상태 OFF · 필터를 켜고 설정 저장을 누르세요"); return ScanState.INACTIVE }
        // RecyclerView can reuse nodes during a fling. Request fresh framework data.
        val root = try {
            if (Build.VERSION.SDK_INT>=33) clearCache()
            rootInActiveWindow
        } catch (error: Exception) {
            clearGeometry(); FilterStatus.update("전면 창 갱신 실패 (${error.javaClass.simpleName})")
            return ScanState.UNAVAILABLE
        }
        if (root == null) { clearGeometry(); FilterStatus.update("전면 창을 확인할 수 없습니다"); return ScanState.UNAVAILABLE }
        try {
            if (root.packageName?.toString() != "com.kakao.talk") { clearGeometry(); FilterStatus.update(if (FilterStatus.diagnosticPending) "진단 대기 · 카카오톡 채팅방을 열고 돌아오세요" else "현재 다른 앱/설정 화면 · 가림막 일시 중지"); return ScanState.INACTIVE }
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
            fun diagnose(conversation: Boolean, reason: String, viewport: Box?=null, result: dev.kakaofilter.core.FilterResult?=null) {
                if (FilterStatus.diagnosticPending) FilterStatus.saveDiagnostics(ScreenDiagnostics.create(nodes,rules,resources.displayMetrics.density,Build.VERSION.SDK_INT,BuildConfig.VERSION_NAME,conversation,truncated,reason,viewport,result))
            }
            if (truncated || nodes.isEmpty()) {
                clearGeometry()
                val reason="화면 구조가 너무 크거나 불완전해 가리지 않았습니다"
                diagnose(false,reason); FilterStatus.result(reason); return ScanState.KAKAO
            }
            val density = resources.displayMetrics.density
            val rootBox = nodes[0].bounds
            val conversation = nodes.any { it.visible && it.editable && it.bounds.top > rootBox.top+rootBox.height*.55 && it.bounds.width > rootBox.width*.3 }
            if (!conversation) {
                clearGeometry()
                val reason="채팅 입력창을 찾지 못함 · 화면 요소 ${nodes.size}개 / 편집 영역 ${nodes.count { it.visible && it.editable }}개"
                diagnose(false,reason); FilterStatus.result(reason); return ScanState.KAKAO
            }
            val listBounds = nodes.filter { !it.editable && (it.scrollable || it.className.endsWith("RecyclerView") || it.className.endsWith("ListView")) && it.bounds.width >= rootBox.width*.7 && it.bounds.height >= 120*density }
                .maxByOrNull { it.bounds.area }?.bounds?.clip(rootBox)
                ?: Box(rootBox.left,rootBox.top+(96*density).toInt(),rootBox.right,rootBox.bottom-(80*density).toInt())
            val inputTop=nodes.filter { it.visible && it.editable && it.bounds.width>rootBox.width*.3 }.minOf { it.bounds.top }
            val viewport=listBounds.clip(Box(rootBox.left,rootBox.top,rootBox.right,inputTop)) ?: listBounds
            val titleIds = setOf("title","toolbar_title","chat_title","chat_room_title","room_title","action_bar_title","title_text","title_view","chatroom_name","chat_name")
            val titles = nodes.filter { it.role in titleIds && it.bounds.top < viewport.top && it.text.isNotBlank() }.map { it.text }.distinct()
            val room = titles.singleOrNull()
            val result = FilterEngine.evaluate(nodes,viewport,density,room,rules)
            // A new application may have become active while Android supplied nodes.
            val current = rootInActiveWindow
            val stillCurrent = try { current?.packageName?.toString() == "com.kakao.talk" && current.windowId == root.windowId }
                finally { @Suppress("DEPRECATION") current?.recycle() }
            if (!stillCurrent) { clearGeometry(); return ScanState.UNAVAILABLE }
            if (rules.enabled && rules.rememberMessages && Build.VERSION.SDK_INT>=34 && windowReader!=null) {
                scanVisual(root.windowId,rootBox,nodes,viewport,density,room,rules,result)
                return ScanState.KAKAO
            }
            showMasks(result.masks,viewport,root.windowId,rules.displayMode)
            diagnose(true,result.reason,viewport,result)
            FilterStatus.result("발신자 ${result.senders} · 대상 ${result.matched} · 가림막 ${result.masks.size} · 이름 미확인 프로필 ${result.unnamedProfiles} · 잘린 프로필 ${result.clippedProfiles}\n${result.reason}",result.recognizedNames)
            return ScanState.KAKAO
        } catch (error: Exception) {
            clearGeometry()
            FilterStatus.result("화면 읽기/가림막 오류 (${error.javaClass.simpleName}) · 권한과 카카오톡 버전을 확인하세요")
            return ScanState.UNAVAILABLE
        } finally { @Suppress("DEPRECATION") root.recycle() }
    }
    private fun activeWindow(window: Int): Boolean {
        val power=getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val keyguard=getSystemService(Context.KEYGUARD_SERVICE) as android.app.KeyguardManager
        if (testing || !power.isInteractive || keyguard.isKeyguardLocked) return false
        return runCatching {
            val current=rootInActiveWindow
            try { current?.packageName?.toString()=="com.kakao.talk" && current.windowId==window }
            finally { @Suppress("DEPRECATION") current?.recycle() }
        }.getOrDefault(false)
    }
    private fun scanVisual(window: Int, rootBox: Box, nodes: List<UiNode>, viewport: Box, density: Float, room: String?, rules: Rules, base: FilterResult) {
        fun toolbarNode(index: Int): Boolean {
            var parent=index
            repeat(50) {
                if (parent !in nodes.indices) return false
                val node=nodes[parent]
                if (node.scrollable || node.className.endsWith("RecyclerView") || node.className.endsWith("ListView")) return false
                if (node.role.contains("toolbar") || node.role.contains("action_bar") || node.className.endsWith("Toolbar")) return true
                parent=node.parent
            }
            return false
        }
        val header=nodes.withIndex().filter { (i,n) -> n.visible && !n.editable && n.bounds.bottom<=viewport.top && n.text.isNotBlank() && toolbarNode(i) }.map { it.value.text }.distinct().sorted().joinToString("\u0000")
        val identity=MessageDigest.getInstance("SHA-256").digest("$window:${rootBox.width}:${rootBox.height}:${room ?: header.ifEmpty { "navigation:$navigation" }}".toByteArray()).joinToString("") { "%02x".format(it) }
        if (identity!=chatIdentity) { chatIdentity=identity;visualSession.clear();clearGeometry() }
        if (scrollingMasks.boxes.isEmpty() && base.masks.isNotEmpty()) showMasks(base.masks,viewport,window,rules.displayMode)
        if (captureBusy || SystemClock.uptimeMillis()-lastCaptureAt<400) return
        val origins=mutableListOf(rootBox)
        windows.firstOrNull { it.id==window }?.let { info -> val r=Rect();info.getBoundsInScreen(r);origins.add(0,Box(r.left,r.top,r.right,r.bottom)) }
        val display=getSystemService(Context.WINDOW_SERVICE) as android.view.WindowManager
        if (Build.VERSION.SDK_INT>=30) { val r=display.currentWindowMetrics.bounds;origins+=Box(r.left,r.top,r.right,r.bottom) }
        val snapshotRevision=revision
        captureBusy=true;lastCaptureAt=SystemClock.uptimeMillis()
        fun current()=snapshotRevision==revision && chatIdentity==identity && store.load()==rules && activeWindow(window)
        fun diagnose(result: FilterResult, structure: List<UiNode>) {
            if (FilterStatus.diagnosticPending) FilterStatus.saveDiagnostics(ScreenDiagnostics.create(structure,rules,density,Build.VERSION.SDK_INT,BuildConfig.VERSION_NAME,true,false,result.reason,viewport,result))
        }
        fun finish(action: () -> Unit) {
            captureBusy=false
            if (!current()) { schedule();return }
            try { action() }
            catch (error: Exception) {
                clearGeometry()
                FilterStatus.result("화면 분석/가림막 오류 (${error.javaClass.simpleName}) · 접근성 서비스를 껐다 켜주세요")
            }
        }
        try {
            windowReader!!.read(window,origins,viewport,density,{ bubbles -> finish {
                val result=visualSession.evaluate(identity,nodes,viewport,density,room,rules,bubbles,scrollingMasks.boxes)
                showMasks(result.filter.masks,viewport,window,rules.displayMode)
                diagnose(result.filter,result.nodes)
                FilterStatus.result("발신자 ${result.filter.senders} · 대상 ${result.filter.matched} · 가림막 ${result.filter.masks.size}\n화면 말풍선 ${result.bubbles} · 기억 ${result.remembered} · 기억 재사용 ${result.reused}\n${result.filter.reason}",result.filter.recognizedNames)
            } },{ reason -> finish {
                showMasks(base.masks,viewport,window,rules.displayMode)
                diagnose(base.copy(reason=reason),nodes)
                FilterStatus.result("$reason · 접근성 가림막 ${base.masks.size}개로 처리\n접근성 서비스를 껐다 켜고 다시 확인하세요",base.recognizedNames)
            } })
        } catch (error: Exception) {
            captureBusy=false
            showMasks(base.masks,viewport,window,rules.displayMode)
            FilterStatus.result("화면 분석 시작 실패 (${error.javaClass.simpleName}) · 접근성 서비스를 껐다 켜주세요",base.recognizedNames)
        }
    }
    fun requestScreenDiagnostics() {
        FilterStatus.requestDiagnostics()
        schedule()
    }
    fun testOverlay() {
        if (!::overlay.isInitialized) return
        testing = true
        clearGeometry()
        scans.stop()
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
    override fun onConfigurationChanged(newConfig: Configuration) { super.onConfigurationChanged(newConfig); if (::overlay.isInitialized) { clearGeometry();visualSession.clear();chatIdentity=null; schedule() } }
    override fun onInterrupt() { testing=false; scans.stop(); handler.removeCallbacks(endTest); clearGeometry();visualSession.clear(); FilterStatus.update("접근성 서비스 일시 중단") }
    override fun onDestroy() {
        scans.stop()
        revision++;visualSession.clear();scrollingMasks.clear()
        if (Build.VERSION.SDK_INT>=34) windowReader?.close()
        handler.removeCallbacksAndMessages(null)
        if (::store.isInitialized) store.preferences.unregisterOnSharedPreferenceChangeListener(changed)
        if (::overlay.isInitialized) overlay.destroy()
        if (receiverRegistered) unregisterReceiver(screen)
        FilterStatus.service = null
        FilterStatus.update("접근성 서비스 꺼짐")
        super.onDestroy()
    }
}
