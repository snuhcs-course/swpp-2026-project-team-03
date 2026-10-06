package com.team3.rocky

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.core.content.FileProvider
import java.io.File

/*
 * ROCKY Iteration 1 시연 설정
 * - 실제 모델 연결 없이, app/src/main/assets/demo/ 에 넣어둔 결과 파일을 보여줍니다.
 * - 파일 이름 규칙: <악기>.png(악보 이미지), <악기>.mp3(악기 음원), <악기>.mid, <악기>.pdf,
 *   original.mp3(원곡), band.mid / band.pdf(밴드 전체, 선택)
 *   악기 이름: piano, drums, bass, guitar
 */
object Demo {
    const val DIR = "demo"

    // 결과 화면 파일 이름: band.png(또는 band-1.png, band-2.png …), band.mp3, band.pdf, band.mid
    const val BAND = "band"
    const val SONG_TITLE = "데모 곡 (Fireflies - Owl City)"

    // 화면에 보이는 순서
    val INSTRUMENTS = listOf("piano", "drums", "bass", "guitar")

    // 원곡에 없어서 AI가 새로 만든 악기 → 결과 화면에 'AI 생성' 표시
    val AI_GENERATED = setOf("piano")

    fun kor(i: String) = when (i) {
        "piano" -> "피아노"; "drums" -> "드럼"; "bass" -> "베이스"; "guitar" -> "기타"; else -> i
    }

    fun emoji(i: String) = when (i) {
        "piano" -> "🎹"; "drums" -> "🥁"; "bass" -> "🎵"; "guitar" -> "🎸"; else -> "🎶"
    }
}

val AUDIO_EXT = listOf("mp3", "wav", "flac", "ogg", "m4a")
val IMG_EXT = listOf("png", "jpg", "jpeg", "webp")

// ---------- 테마 ----------
private val RockyColors = darkColorScheme(
    primary = Color(0xFFFF7A3D),
    onPrimary = Color(0xFF1A1A1A),
    secondary = Color(0xFFFFC857),
    onSecondary = Color(0xFF1A1A1A),
    background = Color(0xFF111114),
    onBackground = Color(0xFFF2F2F2),
    surface = Color(0xFF1C1C22),
    onSurface = Color(0xFFF2F2F2),
    surfaceVariant = Color(0xFF2A2A33),
    onSurfaceVariant = Color(0xFFB4B4C0),
)

@Composable
fun RockyTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = RockyColors, content = content)
}

// ---------- 저장한 작업 (보관함) ----------
data class Work(val id: Long, val title: String, val instruments: List<String>, val date: String)

object WorkStore {
    private const val PREF = "rocky"
    private const val KEY = "works"

    fun load(ctx: Context): List<Work> {
        val raw = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY, "") ?: ""
        return raw.split("\n").filter { it.isNotBlank() }.mapNotNull { line ->
            val p = line.split("\t")
            if (p.size < 4) null
            else Work(p[0].toLongOrNull() ?: 0L, p[1], p[2].split(",").filter { it.isNotBlank() }, p[3])
        }
    }

    fun add(ctx: Context, w: Work) {
        val list = listOf(w) + load(ctx).filter { it.id != w.id }
        val raw = list.joinToString("\n") {
            val title = it.title.replace("\t", " ").replace("\n", " ")
            "${it.id}\t$title\t${it.instruments.joinToString(",")}\t${it.date}"
        }
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString(KEY, raw).apply()
    }
}

// ---------- 데모 파일 ----------
object Assets {
    fun list(ctx: Context): List<String> = ctx.assets.list(Demo.DIR)?.toList() ?: emptyList()

    fun find(ctx: Context, base: String, exts: List<String>): String? {
        val files = list(ctx)
        for (e in exts) {
            val n = "$base.$e"
            if (n in files) return n
        }
        return null
    }

    /** assets 안의 파일을 캐시 폴더로 복사 (재생·공유용) */
    fun toCache(ctx: Context, name: String): File {
        val dir = File(ctx.cacheDir, "share").apply { mkdirs() }
        val out = File(dir, name)
        ctx.assets.open("${Demo.DIR}/$name").use { input ->
            out.outputStream().use { input.copyTo(it) }
        }
        return out
    }
}

fun displayName(ctx: Context, uri: Uri): String {
    var name = "업로드한 곡"
    ctx.contentResolver.query(uri, null, null, null, null)?.use { c ->
        val i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (i >= 0 && c.moveToFirst()) name = c.getString(i) ?: name
    }
    return name.substringBeforeLast('.')
}

private fun mime(name: String) = when (name.substringAfterLast('.').lowercase()) {
    "pdf" -> "application/pdf"
    "mid", "midi" -> "audio/midi"
    "png" -> "image/png"
    else -> "*/*"
}

/** 선택한 파일들을 카카오톡·메일·드라이브 등으로 공유 */
fun shareFiles(ctx: Context, names: List<String>) {
    if (names.isEmpty()) return
    val uris = ArrayList<Uri>(names.map {
        FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", Assets.toCache(ctx, it))
    })
    val intent = if (uris.size == 1) {
        Intent(Intent.ACTION_SEND).apply {
            type = mime(names[0])
            putExtra(Intent.EXTRA_STREAM, uris[0])
        }
    } else {
        Intent(Intent.ACTION_SEND_MULTIPLE).apply {
            type = "*/*"
            putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
        }
    }
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    ctx.startActivity(Intent.createChooser(intent, "ROCKY 악보 공유"))
}
