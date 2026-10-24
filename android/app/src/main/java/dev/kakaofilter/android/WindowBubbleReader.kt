package dev.kakaofilter.android

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.os.Build
import dev.kakaofilter.core.*
import java.util.concurrent.Executors

/** Reads only the requested application window, excluding accessibility overlays. */
class WindowBubbleReader(private val service: AccessibilityService) {
    private val worker=Executors.newSingleThreadExecutor()
    private val fingerprints=BubbleFingerprints()
    fun close() { worker.shutdown() }

    fun read(window: Int, origins: List<Box>, viewport: Box, density: Float,
             success: (List<ReadBubble>) -> Unit, failure: (String) -> Unit) {
        if (Build.VERSION.SDK_INT<34) { failure("화면 분석은 Android 14 이상에서 지원합니다");return }
        service.takeScreenshotOfWindow(window,worker,object : AccessibilityService.TakeScreenshotCallback {
            override fun onFailure(errorCode: Int) { service.mainExecutor.execute { failure("화면 분석 오류 $errorCode") } }
            override fun onSuccess(screenshot: AccessibilityService.ScreenshotResult) {
                var bitmap: Bitmap?=null
                var pixels: IntArray?=null
                val result=runCatching {
                    screenshot.hardwareBuffer.use { buffer ->
                        val hardware=Bitmap.wrapHardwareBuffer(buffer,screenshot.colorSpace) ?: error("buffer")
                        try { bitmap=hardware.copy(Bitmap.Config.ARGB_8888,false) ?: error("copy") }
                        finally { hardware.recycle() }
                    }
                    val image=bitmap ?: error("image")
                    require(image.width.toLong()*image.height<=6_000_000) { "window size" }
                    val origin=origins.firstOrNull { it.width==image.width && it.height==image.height } ?: error("window size")
                    val data=IntArray(image.width*image.height)
                    pixels=data
                    image.getPixels(data,0,image.width,0,0,image.width,image.height)
                    val frame=PixelFrame(image.width,image.height,data,origin.left,origin.top)
                    BubbleDetector.find(frame,viewport,density).map { bubble ->
                        val signature=fingerprints.signature(frame,bubble,density)
                        ReadBubble(bubble.bounds,bubble.incoming,signature?.key,signature?.rows.orEmpty(),bubble.bounds.top<=viewport.top,bubble.bounds.bottom>=viewport.bottom)
                    }
                }
                bitmap?.recycle();pixels?.fill(0)
                service.mainExecutor.execute {
                    result.fold(success) { failure("화면 분석 불가 (${it.javaClass.simpleName})") }
                }
            }
        })
    }
}
