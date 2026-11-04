package com.team3.rocky

import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.graphics.Rect
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.FileProvider
import com.team3.rocky.auth.AuthRepository
import java.io.File

/*
 * ROCKY 시연 설정
 * - 실제 모델 연결 없이, app/src/main/assets/demo/ 에 넣어둔 결과 파일을 보여줍니다.
 * - 파일 이름 규칙: <악기>.png(악보 이미지, 여러 장이면 <악기>-1.png …), <악기>.mp3(악기 음원),
 *   band.mid / band.pdf / band.mp3(밴드 전체)
 *   악기 이름: piano, drums, bass, guitar
 */
object Demo {
    const val DIR = "demo"

    // 결과 화면 파일 이름: band.png(또는 band-1.png, band-2.png …), band.mp3, band.pdf, band.mid
    const val BAND = "band"
    const val SONG_TITLE = "데모 곡 (Immigrant Song - Led Zeppelin)"

    const val GUITAR2 = "guitar2"
    const val VOCAL = "vocal"

    /** 밴드 구성 화면에 보이는 악기. 기타는 두 번 누르면 두 대(guitar + guitar2)가 된다. */
    val INSTRUMENTS = listOf("piano", "drums", "bass", "guitar")

    /** 악보가 나오는 순서. */
    val SCORE_ORDER = listOf("piano", "drums", "bass", "guitar", GUITAR2)

    /** 사람이 맡을 수 있는 파트 (회원 정보, 밴드의 내 파트). 보컬은 악보 없이 밴드 전체 악보를 본다. */
    val PARTS = listOf("piano", "drums", "bass", "guitar", VOCAL)

    /** 데모 곡(Immigrant Song)의 원곡 구성. 피아노가 없어서 피아노를 AI가 만든다. */
    val DEMO_ORIGINAL = listOf("drums", "bass", "guitar")

    // 원곡 구성을 모르는 예전 작업에서 'AI 생성'으로 표시할 악기
    private val LEGACY_AI_GENERATED = setOf("piano")

    fun kor(i: String) = when (i) {
        "piano" -> "피아노"; "drums" -> "드럼"; "bass" -> "베이스"; "guitar" -> "기타"
        GUITAR2 -> "기타 2"; VOCAL -> "보컬"; else -> i
    }

    /** 기타가 두 대인 곡에서는 첫 번째 기타를 '기타 1'로 부른다. */
    fun label(i: String, all: Collection<String>) =
        if (i == "guitar" && GUITAR2 in all) "기타 1" else kor(i)

    /** 악기 목록을 '피아노 · 드럼 · 기타 1 · 기타 2'처럼 이어 쓴다. */
    fun labels(all: List<String>) = all.joinToString(" · ") { label(it, all) }

    /** 결과 파일 이름. 기타 2는 아직 따로 만든 파일이 없어서 기타 파일을 함께 쓴다. */
    fun assetBase(i: String) = if (i == GUITAR2) "guitar" else i

    /** 밴드 구성에서 악기 칸을 누를 때: 켜기/끄기. 기타는 켜면 1대, 끄면 2대였어도 모두 뺀다. */
    fun toggleLineup(current: Set<String>, inst: String): Set<String> = when {
        inst != "guitar" -> if (inst in current) current - inst else current + inst
        "guitar" in current -> current - "guitar" - GUITAR2
        else -> current + "guitar"
    }

    /** 기타 칸의 − / + 버튼. 1대 또는 2대로 맞춘다. */
    fun setGuitarCount(current: Set<String>, count: Int): Set<String> = when (count) {
        2 -> current + "guitar" + GUITAR2
        1 -> current + "guitar" - GUITAR2
        else -> current - "guitar" - GUITAR2
    }

    fun guitarCount(lineup: Set<String>) = when {
        GUITAR2 in lineup -> 2; "guitar" in lineup -> 1; else -> 0
    }

    /** 밴드 멤버들이 맡은 파트로 밴드 구성을 만든다. 보컬은 빼고, 기타가 둘 이상이면 두 대로 본다. */
    fun lineupOf(parts: List<String>): Set<String> {
        val set = parts.filter { it in INSTRUMENTS }.toMutableSet()
        if (parts.count { it == "guitar" } >= 2) set += GUITAR2
        return set
    }

    /** 원곡에 없어서 AI가 새로 만드는 파트. 원곡 구성을 모르면 데모 곡 기준으로 본다. */
    fun aiGenerated(lineup: List<String>, original: List<String>): Set<String> =
        if (original.isEmpty()) lineup.filter { it in LEGACY_AI_GENERATED }.toSet()
        else lineup.filter { it !in original }.toSet()

    fun ordered(set: Collection<String>) = SCORE_ORDER.filter { it in set }
}

val AUDIO_EXT = listOf("mp3", "wav", "flac", "ogg", "m4a")
val IMG_EXT = listOf("png", "jpg", "jpeg", "webp")

// ---------- 화면 모드 (다크 / 라이트) ----------
object AppSettings {
    private const val PREF = "rocky_settings"
    private const val KEY_DARK = "dark_mode"

    var dark by mutableStateOf(true)
        private set

    fun load(ctx: Context) {
        dark = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getBoolean(KEY_DARK, true)
    }

    fun setDark(ctx: Context, value: Boolean) {
        dark = value
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putBoolean(KEY_DARK, value).apply()
    }
}

// ---------- 저장한 작업 (보관함) ----------
/**
 * @param instruments 악보로 만든 파트 (우리 밴드 구성)
 * @param original 원곡에 있던 파트. 비어 있으면 모르는 것으로 본다.
 */
data class Work(
    val id: Long,
    val title: String,
    val instruments: List<String>,
    val date: String,
    val original: List<String> = emptyList(),
) {
    val aiGenerated: Set<String> get() = Demo.aiGenerated(instruments, original)
}

object WorkStore {
    private const val PREF = "rocky"

    // 보관함은 회원마다 따로 저장한다. 로그인 전에는 쓰지 않는다.
    private fun key(ctx: Context) = "works_" + (AuthRepository.currentUserId(ctx) ?: "guest")

    fun load(ctx: Context): List<Work> {
        val raw = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(key(ctx), "") ?: ""
        return raw.split("\n").filter { it.isNotBlank() }.mapNotNull { line ->
            val p = line.split("\t")
            if (p.size < 4) null
            else Work(
                id = p[0].toLongOrNull() ?: 0L,
                title = p[1],
                instruments = p[2].split(",").filter { it.isNotBlank() },
                date = p[3],
                original = p.getOrNull(4).orEmpty().split(",").filter { it.isNotBlank() },
            )
        }
    }

    fun add(ctx: Context, w: Work) = save(ctx, listOf(w) + load(ctx).filter { it.id != w.id })

    fun rename(ctx: Context, id: Long, title: String) =
        save(ctx, load(ctx).map { if (it.id == id) it.copy(title = title) else it })

    fun remove(ctx: Context, id: Long) = save(ctx, load(ctx).filter { it.id != id })

    private fun save(ctx: Context, list: List<Work>) {
        val raw = list.joinToString("\n") {
            val title = it.title.replace("\t", " ").replace("\n", " ")
            "${it.id}\t$title\t${it.instruments.joinToString(",")}\t${it.date}\t${it.original.joinToString(",")}"
        }
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString(key(ctx), raw).apply()
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

    /** 악보 이미지 파일 이름을 쪽 순서대로. base.png 또는 base-1.png, base-2.png … */
    fun pages(ctx: Context, base: String): List<String> {
        val pageNo = Regex("^${Regex.escape(base)}(-(\\d+))?\\.(png|jpg|jpeg|webp)$")
        return list(ctx)
            .mapNotNull { n -> pageNo.find(n)?.let { m -> (m.groupValues[2].toIntOrNull() ?: 0) to n } }
            .sortedBy { it.first }
            .map { it.second }
    }

    /** assets 안의 파일을 캐시 폴더로 복사 (재생·공유용). [outName]을 주면 그 이름으로 저장한다. */
    fun toCache(ctx: Context, name: String, outName: String = name): File {
        val out = File(shareDir(ctx), outName)
        ctx.assets.open("${Demo.DIR}/$name").use { input ->
            out.outputStream().use { input.copyTo(it) }
        }
        return out
    }

    /** 악보 이미지들을 한 PDF로 묶는다 (A4, 쪽마다 이미지 한 장). */
    fun pagesToPdf(ctx: Context, base: String, outName: String): File? {
        val names = pages(ctx, base)
        if (names.isEmpty()) return null
        val doc = PdfDocument()
        try {
            names.forEachIndexed { i, n ->
                val bmp = ctx.assets.open("${Demo.DIR}/$n").use { BitmapFactory.decodeStream(it) } ?: return@forEachIndexed
                val w = 595
                val h = 842
                val page = doc.startPage(PdfDocument.PageInfo.Builder(w, h, i + 1).create())
                val scale = minOf(w.toFloat() / bmp.width, h.toFloat() / bmp.height)
                val dw = (bmp.width * scale).toInt()
                val dh = (bmp.height * scale).toInt()
                page.canvas.drawColor(android.graphics.Color.WHITE)
                page.canvas.drawBitmap(bmp, null, Rect((w - dw) / 2, 0, (w + dw) / 2, dh), null)
                doc.finishPage(page)
                bmp.recycle()
            }
            val out = File(shareDir(ctx), outName)
            out.outputStream().use { doc.writeTo(it) }
            return out
        } finally {
            doc.close()
        }
    }

    private fun shareDir(ctx: Context) = File(ctx.cacheDir, "share").apply { mkdirs() }
}

fun displayName(ctx: Context, uri: Uri): String {
    var name = "업로드한 곡"
    ctx.contentResolver.query(uri, null, null, null, null)?.use { c ->
        val i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (i >= 0 && c.moveToFirst()) name = c.getString(i) ?: name
    }
    return name.substringBeforeLast('.')
}

/** 파일 이름 그대로 (확장자 포함). 서버가 확장자로 음원 형식을 판단한다. */
fun fileName(ctx: Context, uri: Uri): String {
    var name: String? = null
    ctx.contentResolver.query(uri, null, null, null, null)?.use { c ->
        val i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (i >= 0 && c.moveToFirst()) name = c.getString(i)
    }
    val n = name ?: uri.lastPathSegment?.substringAfterLast('/') ?: "song"
    if ('.' in n) return n
    // 이름에 확장자가 없으면 MIME 종류로 붙인다.
    val ext = when (ctx.contentResolver.getType(uri)) {
        "audio/mpeg" -> "mp3"; "audio/wav", "audio/x-wav", "audio/wave" -> "wav"
        "audio/flac", "audio/x-flac" -> "flac"; "audio/mp4", "audio/x-m4a", "audio/aac" -> "m4a"
        "audio/ogg" -> "ogg"; else -> "mp3"
    }
    return "$n.$ext"
}

/** 파일 이름에 쓸 수 없는 글자를 지운다. */
fun safeFileName(s: String) = s.replace(Regex("[\\\\/:*?\"<>|\\t\\n]"), " ").trim().take(60).ifEmpty { "ROCKY" }

private fun mime(name: String) = when (name.substringAfterLast('.').lowercase()) {
    "pdf" -> "application/pdf"
    "mid", "midi" -> "audio/midi"
    "mp3" -> "audio/mpeg"
    "png" -> "image/png"
    else -> "*/*"
}

/** 파일들을 카카오톡·메일·드라이브 등으로 공유 */
fun shareFiles(ctx: Context, files: List<File>) {
    if (files.isEmpty()) return
    val uris = ArrayList<Uri>(files.map { FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", it) })
    val intent = if (uris.size == 1) {
        Intent(Intent.ACTION_SEND).apply {
            type = mime(files[0].name)
            putExtra(Intent.EXTRA_STREAM, uris[0])
        }
    } else {
        Intent(Intent.ACTION_SEND_MULTIPLE).apply {
            type = "*/*"
            putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
        }
    }
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    ctx.startActivity(Intent.createChooser(intent, "ROCKY 악보 내보내기"))
}
