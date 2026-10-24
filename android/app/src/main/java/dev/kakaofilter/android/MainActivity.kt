package dev.kakaofilter.android

import android.app.Activity
import android.app.AlertDialog
import android.content.ComponentName
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.View
import android.view.WindowInsets
import android.widget.*
import dev.kakaofilter.core.Rules
import dev.kakaofilter.core.normalized

class MainActivity : Activity() {
    private lateinit var store: SettingsStore
    private lateinit var enabled: Switch
    private lateinit var allChats: CheckBox
    private lateinit var images: CheckBox
    private lateinit var remember: CheckBox
    private var screenAnalysisConsent=false
    private lateinit var names: EditText
    private lateinit var rooms: EditText
    private lateinit var mode: Spinner
    private lateinit var status: TextView
    private lateinit var recognized: TextView
    private lateinit var savedStatus: TextView
    private lateinit var diagnosticStatus: TextView
    private val handler = Handler(Looper.getMainLooper())
    private val statusChanged: () -> Unit = { updateStatus() }
    private val refresh = object : Runnable { override fun run() { updateStatus(); handler.postDelayed(this,1000) } }
    private fun dp(value: Int) = (value*resources.displayMetrics.density).toInt()
    private fun accessibilityEnabled(): Boolean {
        val component = ComponentName(this,FilterAccessibilityService::class.java)
        return Settings.Secure.getString(contentResolver,Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty().split(':').any { ComponentName.unflattenFromString(it) == component }
    }
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        store = SettingsStore(this)
        val scroll = ScrollView(this)
        val panel = LinearLayout(this).apply { orientation=LinearLayout.VERTICAL; setBackgroundColor(Color.rgb(247,249,246)); setPadding(dp(20),dp(20),dp(20),dp(24)) }
        scroll.addView(panel)
        scroll.setOnApplyWindowInsetsListener { _, insets ->
            @Suppress("DEPRECATION")
            val edges = if (android.os.Build.VERSION.SDK_INT>=30) {
                val bars=insets.getInsets(WindowInsets.Type.systemBars())
                intArrayOf(bars.left,bars.top,bars.right,bars.bottom)
            } else intArrayOf(insets.systemWindowInsetLeft,insets.systemWindowInsetTop,insets.systemWindowInsetRight,insets.systemWindowInsetBottom)
            panel.setPadding(dp(20)+edges[0],dp(20)+edges[1],dp(20)+edges[2],dp(24)+edges[3])
            insets
        }
        setContentView(scroll)
        fun label(text: String, size: Float=14f) = TextView(this).apply { this.text=text; textSize=size; setTextColor(Color.rgb(34,49,41)); setPadding(0,dp(10),0,dp(8)); panel.addView(this) }
        fun button(text: String, action: () -> Unit) = Button(this).apply { this.text=text; isAllCaps=false; panel.addView(this,LinearLayout.LayoutParams(-1,-2)); setOnClickListener { action() } }
        label("카카오 메시지 필터",25f)
        label("Android ${BuildConfig.VERSION_NAME} · 접근성 기반 실험 버전\n내 화면에만 가림막을 표시합니다. 서버 메시지는 바뀌지 않습니다.")
        remember=CheckBox(this).apply {
            text="메시지 기억 · 연속 말풍선 보완 (화면 분석 사용)"
            isEnabled=android.os.Build.VERSION.SDK_INT>=34
            panel.addView(this)
        }
        label("Android 14 이상·기본 밝은 테마용. 확인한 메시지의 표식과 주변 메시지를 메모리에서 기억하고, 스크롤 이동량으로 가림막을 옮깁니다. 앱 종료·설정 변경 시 기억은 지워집니다. 처음부터 발신자를 못 읽은 메시지는 기억할 수 없습니다.")
        screenAnalysisConsent=store.load().rememberMessages
        remember.setOnCheckedChangeListener { _, checked ->
            if (!checked) {
                if (store.load().rememberMessages) store.save(store.load().copy(rememberMessages=false))
                screenAnalysisConsent=false
            }
            if (checked && !screenAnalysisConsent) {
                remember.isChecked=false
                AlertDialog.Builder(this).setTitle("카카오톡 창 화면 분석")
                    .setMessage("연속 말풍선을 찾고 스크롤 후에도 기억한 메시지를 가리기 위해 카카오톡 창 이미지를 기기 안에서 분석합니다. 다른 앱과 보안 처리된 창은 분석하지 않습니다. 이미지와 메시지 원문은 저장·전송하지 않고 즉시 버리며, 메시지 표식만 앱 실행 중 메모리에 남깁니다.\n\n이 기능을 켜고 설정을 저장할까요?")
                    .setNegativeButton("취소",null).setPositiveButton("동의하고 켜기") { _, _ -> screenAnalysisConsent=true;remember.isChecked=true;toast("설정 저장 및 적용을 눌러주세요") }.show()
            }
        }
        status=label("접근성 서비스 확인 중")
        savedStatus=label("")
        recognized=label("")
        diagnosticStatus=label("")
        button("문제 화면 진단 시작") {
            val service=FilterStatus.service?.get()
            if (service==null) toast("먼저 접근성 서비스를 켜주세요")
            else { service.requestScreenDiagnostics(); toast("카카오톡에서 안 가려지는 메시지를 보이게 한 뒤 돌아와 바로 아래의 진단 파일 저장을 누르세요. 원문은 기록하지 않습니다.") }
        }
        button("진단 파일 저장 (메시지 원문 제외)") {
            if (FilterStatus.diagnostics.isEmpty()) toast("먼저 진단 시작을 누르고 카카오톡 채팅방을 열어주세요")
            else startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply { type="application/json"; addCategory(Intent.CATEGORY_OPENABLE); putExtra(Intent.EXTRA_TITLE,"kakao-screen-structure.json") },12)
        }
        CheckBox(this).apply {
            text="인식한 닉네임 표시 (진단용 · 메모리에만 유지)"
            isChecked=FilterStatus.showNames
            setOnCheckedChangeListener { _, checked -> FilterStatus.namesVisible(checked) }
            panel.addView(this)
        }
        button("인식한 이름 선택해서 숨김 목록에 추가") { chooseRecognizedName() }
        label("접근성 권한으로 카카오톡의 발신자와 메시지 위치를 읽습니다. 상단의 메시지 기억 옵션을 직접 켜면 카카오톡 창 이미지를 기기 메모리에서 분석합니다. 원문·이미지는 저장하거나 전송하지 않습니다. 가림막은 터치와 스크롤을 통과시킵니다.")
        button("동의하고 접근성 설정 열기") {
            AlertDialog.Builder(this).setTitle("접근성 사용 안내")
                .setMessage("이 앱은 카카오톡 화면의 접근성 정보(발신자, 메시지 위치, 채팅방 제목)를 읽어 지정한 메시지 위에 가림막을 표시합니다. 메시지 기억 옵션에 별도 동의하면 카카오톡 창 이미지를 메모리에서 분석합니다. 다른 앱의 화면은 분석하지 않으며, 메시지와 이미지를 저장하거나 전송하지 않습니다.\n\n다음 설정 화면에서 '카카오 메시지 필터' 서비스를 직접 켜주세요. 언제든 이 화면에서 중지하거나 시스템 설정에서 권한을 끌 수 있습니다.")
                .setNegativeButton("취소",null).setPositiveButton("동의하고 설정으로") { _, _ -> startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }.show()
        }
        button("가림막 표시 테스트 · 5초") {
            val service=FilterStatus.service?.get()
            if (service==null) toast("먼저 접근성 서비스를 켜주세요") else service.testOverlay()
        }
        enabled=Switch(this).apply { text="필터 켜기 (저장 후 적용)"; panel.addView(this) }
        label("숨길 닉네임 · 한 줄에 한 명")
        names=EditText(this).apply { hint="정민욱"; minLines=3; gravity=android.view.Gravity.TOP; inputType=android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE; panel.addView(this) }
        label("동명이인은 구별할 수 없습니다. 발신자 정보가 없는 메시지는 추측하지 않습니다.")
        allChats=CheckBox(this).apply { text="모든 카카오톡 채팅방에 적용 (개인방 포함)"; panel.addView(this) }
        label("선택할 채팅방 제목 · 한 줄에 하나, 정확히 입력")
        rooms=EditText(this).apply { minLines=2; gravity=android.view.Gravity.TOP; inputType=android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE; panel.addView(this) }
        label("표시 방식")
        mode=Spinner(this).apply { adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,listOf("완전 가림","숨긴 메시지 안내문")); panel.addView(this) }
        images=CheckBox(this).apply { text="같은 발신자의 사진·이모티콘도 가리기"; panel.addView(this) }
        button("설정 저장 및 적용") {
            runCatching {
                val rules=readFields()
                require(!rules.enabled || rules.hiddenUsers.isNotEmpty()) { "숨길 닉네임을 입력하세요" }
                require(!rules.enabled || rules.allChats || rules.selectedChats.isNotEmpty()) { "채팅방 제목을 입력하거나 모든 채팅방 적용을 선택하세요" }
                store.save(rules)
                toast(if (accessibilityEnabled()) "저장했습니다. 카카오톡 채팅방을 앞으로 가져오세요" else "저장했습니다. 접근성 서비스도 켜주세요")
            }.onFailure { toast(it.message ?: "설정 오류") }
        }
        button("지금 필터 중지") { enabled.isChecked=false; store.save(store.load().copy(enabled=false)); toast("필터를 중지했습니다") }
        button("PC 설정 JSON 가져오기") { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type="*/*"; addCategory(Intent.CATEGORY_OPENABLE) },10) }
        button("설정 JSON 내보내기") { startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply { type="application/json"; addCategory(Intent.CATEGORY_OPENABLE); putExtra(Intent.EXTRA_TITLE,"kakao-filter-settings.json") },11) }
        label("지원 범위\n발신자 확인은 접근성 정보를 사용합니다. 메시지 기억 옵션은 흰색 수신/노란색 발신 말풍선을 화면 분석으로 보완합니다. 테마·글꼴·창 크기가 바뀌거나 메시지가 수정되면 새 확인이 필요합니다. 스크롤 중 순간 노출을 완전히 막는 보안 기능은 아닙니다.\n\nAndroid 13 이상에서 권한이 제한되면 앱 정보의 메뉴에서 '제한된 설정 허용'을 확인하세요. 메뉴 위치는 제조사에 따라 다릅니다.\n\n설정은 기기 내부에 저장합니다. 앱을 삭제하면 사라지므로 필요하면 JSON을 내보내세요.")
        setFields(store.load())
        enabled.setOnCheckedChangeListener { _, checked -> if (!checked) store.save(store.load().copy(enabled=false)) }
    }
    private fun chooseRecognizedName() {
        val found=FilterStatus.lastNames.toList()
        if (!FilterStatus.showNames || found.isEmpty()) { toast("닉네임 표시를 켜고 카카오톡 채팅방을 연 뒤 돌아오세요. 읽은 이름이 없으면 화면 구조 진단을 사용하세요."); return }
        fun display(value: String) = "「"+value.replace("\u200b","[U+200B]").replace("\ufeff","[U+FEFF]")+"」"
        AlertDialog.Builder(this).setTitle("실제로 읽은 이름 선택")
            .setItems(found.map(::display).toTypedArray()) { _, which ->
                val value=found[which]
                val current=names.text.lines().map(::normalized).filter { it.isNotBlank() }
                if (value in current) { toast("이미 숨김 목록에 있는 이름입니다. 마지막 결과의 프로필 잘림/메시지 영역 안내를 확인하세요."); return@setItems }
                val updated=current.distinct().toMutableList()
                updated.add(value)
                names.setText(updated.joinToString("\n"))
                toast("선택한 이름을 추가했습니다. 실제 대상인지 확인한 뒤 설정 저장 및 적용을 누르세요.")
            }.setNegativeButton("취소",null).show()
    }
    private fun readFields(): Rules = Rules(enabled.isChecked,names.text.lines().map(::normalized).filter { it.isNotEmpty() }.distinct(),rooms.text.lines().map(::normalized).filter { it.isNotEmpty() }.distinct(),allChats.isChecked,images.isChecked,if (mode.selectedItemPosition==1) "placeholder" else "opaque",remember.isChecked && screenAnalysisConsent && android.os.Build.VERSION.SDK_INT>=34)
    private fun setFields(r: Rules) { enabled.isChecked=r.enabled; names.setText(r.hiddenUsers.joinToString("\n")); rooms.setText(r.selectedChats.joinToString("\n")); allChats.isChecked=r.allChats; images.isChecked=r.hideImages; mode.setSelection(if (r.displayMode=="placeholder") 1 else 0);remember.isChecked=r.rememberMessages && screenAnalysisConsent }
    private fun toast(text: String) { Toast.makeText(this,text,Toast.LENGTH_LONG).show() }
    private fun updateStatus() {
        if (::status.isInitialized) {
            status.text=getString(R.string.status_line,
                getString(if (accessibilityEnabled()) R.string.status_enabled else R.string.status_disabled),
                FilterStatus.message,FilterStatus.lastResult.ifEmpty { getString(R.string.last_none) })
            val rules=store.load()
            savedStatus.text=getString(R.string.saved_line,getString(if (rules.enabled) R.string.status_enabled else R.string.status_disabled),rules.hiddenUsers.size,if (rules.allChats) "모든 방" else "선택한 방")
            diagnosticStatus.text=if (FilterStatus.diagnostics.isNotEmpty()) getString(R.string.diagnostic_ready) else ""
            recognized.text=if (FilterStatus.showNames) getString(R.string.recognized_line,FilterStatus.lastNames.joinToString(" / ") { "「$it」" }.ifEmpty { "아직 없음 · 카카오톡 채팅방을 열어주세요" }) else ""
        }
    }
    @Deprecated("Platform result API")
    override fun onActivityResult(requestCode: Int,resultCode: Int,data: Intent?) {
        super.onActivityResult(requestCode,resultCode,data)
        if (resultCode!=RESULT_OK) return
        val uri=data?.data ?: return
        runCatching {
            if (requestCode==10) {
                val input=contentResolver.openInputStream(uri) ?: error("파일을 열 수 없습니다")
                val buffer=ByteArray(65537)
                var length=0
                input.use { while (length<buffer.size) { val count=it.read(buffer,length,buffer.size-length); if (count<0) break; if (count==0) error("파일을 읽을 수 없습니다"); length+=count } }
                require(length<=65536) { "64KB 이하의 설정 파일을 선택하세요" }
                val imported=SettingsStore.decode(String(buffer,0,length,Charsets.UTF_8)).copy(enabled=false,rememberMessages=false)
                setFields(imported); store.save(imported); toast("가져왔습니다. 내용을 확인한 뒤 필터를 켜고 저장하세요. 흐림 옵션은 완전 가림으로 변환합니다.")
            } else if (requestCode==12) {
                val diagnostic=FilterStatus.diagnostics
                require(diagnostic.isNotEmpty()) { "진단 결과가 없습니다. 진단을 다시 시작하세요" }
                val output=contentResolver.openOutputStream(uri,"wt") ?: error("파일을 저장할 수 없습니다")
                output.use { it.write(diagnostic.toByteArray(Charsets.UTF_8)) }
                toast("화면 구조 진단을 저장했습니다. 이름/메시지 원문은 포함하지 않습니다.")
            } else if (requestCode==11) {
                val output=contentResolver.openOutputStream(uri,"wt") ?: error("파일을 저장할 수 없습니다")
                output.use { it.write(SettingsStore.encode(readFields()).toByteArray(Charsets.UTF_8)) }
                toast("설정을 내보냈습니다")
            }
        }.onFailure { toast(it.message ?: "파일 처리 실패") }
    }
    override fun onResume() { super.onResume(); FilterStatus.listeners+=statusChanged; handler.post(refresh) }
    override fun onPause() { handler.removeCallbacks(refresh); FilterStatus.listeners-=statusChanged; super.onPause() }
}
