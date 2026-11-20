package com.team3.rocky

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import android.util.LruCache
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.File

/** 이보다 긴 악보는 앞부분만 그린다 (전체 악보도 보통 40쪽 안쪽). */
const val MAX_SCORE_PAGES = 60

/**
 * 화면 폭으로 그려 빈 여백을 잘라낸 악보 페이지들.
 * [widths]는 PDF를 그린 폭, [crops]는 잘라낸 만큼 (왼쪽, 위) px. 서버의 마디 위치를 그림 좌표로 옮길 때 쓴다.
 */
class ScorePages(
    val images: List<ImageBitmap>,
    val bitmaps: List<Bitmap>,
    val widths: List<Int>,
    val crops: List<Pair<Int, Int>>,
) {
    val bytes: Int get() = bitmaps.sumOf { it.allocationByteCount }

    companion object {
        val EMPTY = ScorePages(emptyList(), emptyList(), emptyList(), emptyList())
    }
}

/**
 * 한 번 그린 악보 페이지를 기억해 둔다. 악기를 바꿨다가 돌아오면 다시 그리지 않는다.
 * 160MB까지 쓰고, 넘으면 가장 오래 안 본 악보부터 버린다. 비트맵은 Java 힙이 아니라 네이티브 메모리에
 * 있어서 Java 힙 한도(maxMemory)로 정하면 너무 작다 (전체 악보 31쪽이 약 90MB).
 */
object ScorePageCache {
    private const val BUDGET_BYTES = 160 * 1024 * 1024
    private val cache = object : LruCache<String, ScorePages>(BUDGET_BYTES) {
        override fun sizeOf(key: String, value: ScorePages) = value.bytes.coerceAtLeast(1)
    }

    /** 같은 파일이라도 다시 받으면(크기·시각이 바뀌면) 새로 그린다. 화면 폭이 다르면 따로 둔다. */
    fun key(file: File, widthPx: Int) = "${file.absolutePath}:${file.length()}:${file.lastModified()}:$widthPx"

    fun get(key: String): ScorePages? = cache.get(key)

    fun put(key: String, pages: ScorePages) {
        cache.put(key, pages)
    }
}

/**
 * PDF를 한 쪽씩 그려서, 그릴 때마다(처음 두 쪽은 바로, 그 뒤로는 4쪽마다) [onProgress]로 알린다.
 * 첫 쪽이 거의 바로 보이고, 나머지는 보는 동안 이어서 그려진다.
 * 악보는 흑백이라 RGB_565로 줄여 둔다 (메모리 절반).
 */
suspend fun renderScorePages(
    file: File,
    widthPx: Int,
    onProgress: suspend (ScorePages) -> Unit,
): ScorePages = withContext(Dispatchers.IO) {
    val images = mutableListOf<ImageBitmap>()
    val bitmaps = mutableListOf<Bitmap>()
    val widths = mutableListOf<Int>()
    val crops = mutableListOf<Pair<Int, Int>>()
    fun snapshot() = ScorePages(images.toList(), bitmaps.toList(), widths.toList(), crops.toList())
    ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { fd ->
        PdfRenderer(fd).use { pdf ->
            val n = minOf(pdf.pageCount, MAX_SCORE_PAGES)
            for (i in 0 until n) {
                ensureActive()
                val full = pdf.openPage(i).use { page ->
                    val h = (widthPx.toFloat() * page.height / page.width).toInt().coerceAtLeast(1)
                    Bitmap.createBitmap(widthPx, h, Bitmap.Config.ARGB_8888).also { bmp ->
                        bmp.eraseColor(Color.WHITE)
                        page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    }
                }
                val crop = marginCrop(full)
                val cut = if (crop == null) full
                else Bitmap.createBitmap(full, crop.left, crop.top, crop.width(), crop.height())
                val small = cut.copy(Bitmap.Config.RGB_565, false)
                if (cut !== full) cut.recycle()
                full.recycle()
                bitmaps += small
                images += small.asImageBitmap()
                widths += widthPx
                crops += (crop?.left ?: 0) to (crop?.top ?: 0)
                if (i < 2 || i == n - 1 || i % 4 == 3) onProgress(snapshot())
            }
        }
    }
    snapshot()
}
