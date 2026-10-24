package dev.kakaofilter.android

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PixelFormat
import android.os.Build
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import dev.kakaofilter.core.Box

class MaskOverlay(private val service: AccessibilityService) {
    private val manager = service.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var attached = false
    private val layer = object : View(service) {
        var boxes: List<Box> = emptyList()
        var mode = "opaque"
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        val origin = IntArray(2)
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            getLocationOnScreen(origin)
            boxes.forEach { box ->
                val left = (box.left-origin[0]).toFloat()
                val top = (box.top-origin[1]).toFloat()
                val right = (box.right-origin[0]).toFloat()
                val bottom = (box.bottom-origin[1]).toFloat()
                paint.color = Color.rgb(61,70,82)
                canvas.drawRect(left, top, right, bottom, paint)
                if (mode == "placeholder") {
                    val saved = canvas.save()
                    canvas.clipRect(left, top, right, bottom)
                    paint.color = Color.WHITE
                    paint.textSize = android.util.TypedValue.applyDimension(android.util.TypedValue.COMPLEX_UNIT_SP,12f,resources.displayMetrics)
                    canvas.drawText("숨긴 메시지입니다", left+8, top+paint.textSize+4, paint)
                    canvas.restoreToCount(saved)
                }
            }
        }
    }
    fun show(boxes: List<Box>, mode: String) {
        if (boxes.isEmpty()) { clear(); return }
        if (!attached) {
            val params = WindowManager.LayoutParams(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT)
            params.gravity = Gravity.TOP or Gravity.START
            if (Build.VERSION.SDK_INT >= 30) params.setFitInsetsTypes(0)
            layer.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
            manager.addView(layer, params)
            attached = true
        }
        layer.boxes = boxes.toList()
        layer.mode = mode
        layer.invalidate()
    }
    fun clear() {
        layer.boxes = emptyList()
        layer.invalidate()
    }
    fun destroy() {
        clear()
        if (attached) { manager.removeViewImmediate(layer); attached = false }
    }
}
