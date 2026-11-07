// AI-generated with Claude Code, 2026-11-07
package com.team3.rocky

import android.Manifest
import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.media.MediaScannerConnection
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.ContextCompat
import java.io.File

/**
 * 악보 파일을 휴대폰의 '다운로드/ROCKY' 폴더에 저장한다. 내 파일 앱에서 바로 찾을 수 있다.
 * - 안드로이드 10 이상: MediaStore로 저장 (권한 필요 없음)
 * - 안드로이드 8~9: 저장 권한이 있어야 한다. 없으면 [needsPermission]이 true
 * 네트워크는 쓰지 않지만 파일을 복사하므로 IO 스레드에서 부를 것.
 */
object PhoneSaver {
    const val FOLDER = "ROCKY"

    /** 화면에 보여줄 저장 위치 */
    fun folderLabel() = tr("내 파일 › 다운로드 › $FOLDER", "My Files › Download › $FOLDER")

    fun needsPermission(ctx: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.Q &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED

    /** 저장한 파일 수를 돌려준다. 같은 이름이 있으면 휴대폰이 알아서 "(1)"을 붙인다. */
    fun save(ctx: Context, files: List<File>): Int {
        var saved = 0
        for (f in files) {
            if (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) saveQ(ctx, f) else saveLegacy(ctx, f)) saved++
        }
        return saved
    }

    private fun saveQ(ctx: Context, file: File): Boolean {
        val resolver = ctx.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, file.name)
            put(MediaStore.MediaColumns.MIME_TYPE, mimeOf(file.name))
            put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/" + FOLDER)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return false
        return try {
            resolver.openOutputStream(uri)?.use { out -> file.inputStream().use { it.copyTo(out) } }
                ?: error("no output stream")
            values.clear()
            values.put(MediaStore.MediaColumns.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            true
        } catch (e: Exception) {
            resolver.delete(uri, null, null)
            false
        }
    }

    @Suppress("DEPRECATION")
    private fun saveLegacy(ctx: Context, file: File): Boolean = try {
        val dir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), FOLDER)
        dir.mkdirs()
        var out = File(dir, file.name)
        var n = 1
        while (out.exists()) {
            out = File(dir, "${file.nameWithoutExtension} ($n).${file.extension}")
            n++
        }
        file.copyTo(out)
        MediaScannerConnection.scanFile(ctx, arrayOf(out.absolutePath), null, null)
        true
    } catch (e: Exception) {
        false
    }

    private fun mimeOf(name: String) = when (name.substringAfterLast('.').lowercase()) {
        "pdf" -> "application/pdf"
        "mid", "midi" -> "audio/midi"
        "mp3" -> "audio/mpeg"
        else -> "application/octet-stream"
    }
}
