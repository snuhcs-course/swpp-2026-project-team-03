package com.team3.rocky

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.team3.rocky.auth.AuthRepository
import java.io.File

/*
 * 악기 이름·밴드 구성 규칙.
 * 악기 이름: piano, drums, bass, guitar (+ 기타 2대면 guitar2, 사람 파트로는 vocal)
 * (이름 Demo는 처음에 시연용 데이터에서 시작해서 남은 것. 시연용 곡·파일은 11/11에 모두 뺐다.)
 */
object Demo {
    /** 결과 화면에서 '밴드 전체'를 가리키는 이름. */
    const val BAND = "band"

    const val GUITAR2 = "guitar2"
    const val VOCAL = "vocal"

    /** 밴드 구성 화면에 보이는 악기. 기타는 두 번 누르면 두 대(guitar + guitar2)가 된다. */
    val INSTRUMENTS = listOf("piano", "drums", "bass", "guitar")

    /** 기타가 아닌 악기. '기타 대수 바꿔서 다시 만들기'에서 모델이 찾은 그대로 원곡 구성으로 보낸다. */
    val NON_GUITAR = listOf("piano", "drums", "bass")

    /**
     * '기타 대수 바꿔서 다시 만들기'의 원곡 구성: 모델이 찾은 원곡 악기 중 기타 아닌 것 + 사용자가 고른 기타 대수.
     * 앱 이름(guitar2 = 두 번째 기타)으로, 서버가 unified.py --original 형식으로 바꾼다.
     */
    /**
     * 개인 연습용에서 기타 대수를 골랐을 때 아래에 보여줄 안내. 원곡 기타 대수와 같게 고르면 가장 치기 좋다.
     * 기타를 안 골랐으면 null.
     */
    fun personalGuitarNote(guitars: Int): String? = when (guitars) {
        1 -> tr(
            "원곡에 기타가 두 대라면 두 기타가 한 악보로 합쳐져서, 혼자 치기엔 조금 어려울 수 있어요.",
            "If the song has two guitars, both are merged into one score, which can be a bit hard to play alone.",
        )
        2 -> tr(
            "원곡에 기타가 한 대라면 두 번째 기타 악보는 AI가 새로 만들어요(✨).",
            "If the song has one guitar, the second guitar score is made with AI (✨).",
        )
        else -> null
    }

    fun redoOriginal(found: List<String>, guitars: Int): List<String> {
        val others = found.filter { it in NON_GUITAR }
        val g = when (guitars) { 0 -> emptyList(); 1 -> listOf("guitar"); else -> listOf("guitar", GUITAR2) }
        return ordered(others + g)
    }

    /** 악보가 나오는 순서. */
    val SCORE_ORDER = listOf("piano", "drums", "bass", "guitar", GUITAR2)

    /** 사람이 맡을 수 있는 파트 (회원 정보, 밴드의 내 파트). 보컬은 악보 없이 밴드 전체 악보를 본다. */
    val PARTS = listOf("piano", "drums", "bass", "guitar", VOCAL)

    // 원곡 구성을 모르는 예전 작업에서 'AI 생성'으로 표시할 악기
    private val LEGACY_AI_GENERATED = setOf("piano")

    /** 악기 이름 (고른 언어로). 예전 이름 kor는 그대로 둔다. */
    fun kor(i: String) = when (i) {
        "piano" -> tr("피아노", "Piano"); "drums" -> tr("드럼", "Drums"); "bass" -> tr("베이스", "Bass")
        "guitar" -> tr("기타", "Guitar"); GUITAR2 -> tr("기타 2", "Guitar 2"); VOCAL -> tr("보컬", "Vocals"); else -> i
    }

    /** 기타가 두 대인 곡에서는 첫 번째 기타를 '기타 1'로 부른다. */
    fun label(i: String, all: Collection<String>) =
        if (i == "guitar" && GUITAR2 in all) tr("기타 1", "Guitar 1") else kor(i)

    /** 악기 목록을 '피아노 · 드럼 · 기타 1 · 기타 2'처럼 이어 쓴다. */
    fun labels(all: List<String>) = all.joinToString(" · ") { label(it, all) }

    /** 아이콘 등에 쓰는 기본 악기 이름. 기타 2는 기타와 같은 것으로 본다. */
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

    /**
     * ⚠️ 표시할 파트: 사용자가 '원곡에 있다'고 골랐는데 원곡에서 소리가 거의 들리지 않은 악기.
     * 서버(파이프라인 note gate)가 [faint]로 알려 준다. 악보는 나오지만 음이 아주 적을 수 있다.
     * '잘 모르겠어요'([claimed]가 비어 있음)면 그런 악기는 원곡에 없는 것으로 처리되므로 표시하지 않는다.
     * 기타가 약하면 우리 밴드의 기타 2도 같은 원곡 기타에서 나오므로 함께 표시한다.
     */
    fun faintParts(lineup: List<String>, claimed: List<String>, faint: List<String>): List<String> {
        if (claimed.isEmpty()) return emptyList()
        val set = faint.filter { it in INSTRUMENTS }.toMutableSet()
        if ("guitar" in set && GUITAR2 in lineup && GUITAR2 in claimed) set += GUITAR2
        return ordered(set.filter { it in lineup && it in claimed })
    }

    /** 원곡에 없어서 AI가 새로 만드는 파트. 원곡 구성을 모르는 예전 작업은 피아노만 그렇게 본다. */
    fun aiGenerated(lineup: List<String>, original: List<String>): Set<String> =
        if (original.isEmpty()) lineup.filter { it in LEGACY_AI_GENERATED }.toSet()
        else lineup.filter { it !in original }.toSet()

    fun ordered(set: Collection<String>) = SCORE_ORDER.filter { it in set }
}

val AUDIO_EXT = listOf("mp3", "wav", "flac", "ogg", "m4a")
val IMG_EXT = listOf("png", "jpg", "jpeg", "webp")

// ---------- 화면 모드 (다크 / 라이트) · 언어 ----------
object AppSettings {
    private const val PREF = "rocky_settings"
    private const val KEY_DARK = "dark_mode"
    private const val KEY_LANG = "language"

    var dark by mutableStateOf(true)
        private set

    /** 앱 문구 언어. 기본은 한국어. */
    var lang by mutableStateOf(Lang.KO)
        private set

    fun load(ctx: Context) {
        val p = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        dark = p.getBoolean(KEY_DARK, true)
        lang = Lang.entries.firstOrNull { it.code == p.getString(KEY_LANG, null) } ?: Lang.KO
    }

    fun setDark(ctx: Context, value: Boolean) {
        dark = value
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putBoolean(KEY_DARK, value).apply()
    }

    fun setLang(ctx: Context, value: Lang) {
        lang = value
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString(KEY_LANG, value.code).apply()
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
    /** 원곡에 있다고 골랐지만 원곡에서 소리가 거의 들리지 않은 파트 (⚠️) */
    val unrecognized: List<String> = emptyList(),
    /** 개인 연습용 (내가 연주할 악기만). false면 밴드 합주용. 개인용은 밴드에 공유하지 않는다. */
    val personal: Boolean = false,
    /** 올린 곡 파일 (content:// 주소). 개인 연습용의 '전체'는 이 원곡을 들려준다. 이 폰에서만 열린다. */
    val audio: String? = null,
) {
    val aiGenerated: Set<String> get() = Demo.aiGenerated(instruments, original) - unrecognized.toSet()
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
                unrecognized = p.getOrNull(5).orEmpty().split(",").filter { it.isNotBlank() },
                personal = p.getOrNull(6) == "1",
                audio = p.getOrNull(7)?.takeIf { it.isNotBlank() },
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
            "${it.id}\t$title\t${it.instruments.joinToString(",")}\t${it.date}\t${it.original.joinToString(",")}" +
                "\t${it.unrecognized.joinToString(",")}\t${if (it.personal) "1" else "0"}\t${it.audio.orEmpty()}"
        }
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString(key(ctx), raw).apply()
    }
}

fun displayName(ctx: Context, uri: Uri): String {
    var name = tr("내 곡", "My song")
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

