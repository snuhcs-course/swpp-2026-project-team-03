// AI-generated with Claude Code, 2026-11-01
package com.team3.rocky.server

import android.content.Context
import java.io.File

/**
 * 서버에서 받은 결과를 폰에 저장해 둔 것. 폴더는 filesDir/scores/<작업 id>/.
 * 작업 id(Work.id)로 찾는다. 다른 밴드원이 공유한 악보는 처음 열 때 서버에서 받아 여기에 둔다.
 * 폴더가 없는 작업은 악보 파일이 없는 것으로 본다.
 */
class LocalScore(
    val dir: File, val result: JobResult, val semitones: Int = 0,
    /** 이 시각(밀리초)까지만 MP3를 들을 수 있다. 서버가 알려 준 값, 모르면 받은 때부터 24시간. */
    val audioUntil: Long = result.audioExpiresAt ?: Long.MAX_VALUE,
) {
    /**
     * 앱의 파트 이름(piano, drums, bass, guitar, guitar2) → 서버 결과의 키.
     * AI가 두 번째 기타를 만든 곡은 guitar_1 / guitar_2가 따로 오고,
     * 원곡에 기타 2대가 있으면 guitar 하나(TAB 두 줄)에 둘 다 들어 있다.
     * null이면 밴드 전체.
     */
    fun key(part: String?): String? = when (part) {
        null -> null
        "guitar" -> if ("guitar_1" in result.instruments) "guitar_1" else "guitar"
        "guitar2" -> if ("guitar_2" in result.instruments) "guitar_2" else "guitar"
        else -> part
    }

    private fun entry(part: String?) = key(part).let { k -> if (k == null) result.fullBand else result.instruments[k] }

    fun pdf(part: String?): File? = file(entry(part)?.pdf)
    fun midi(part: String?): File? = file(entry(part)?.midi)
    fun mp3(part: String?): File? = if (audioAvailable()) file(entry(part)?.mp3) else null
    fun measures(part: String?): File? = file(entry(part)?.measures)

    /**
     * 듣기는 완성 후 24시간만 (베타 저장 공간: 서버가 MP3를 지운다). 그 뒤에는 재생 바를 숨긴다.
     * 악보와 MIDI는 계속 볼 수 있다.
     */
    fun audioAvailable(now: Long = System.currentTimeMillis()) = now < audioUntil

    /** 재생할 파일: MP3가 있으면 MP3, 없으면 MIDI (둘 다 악보로 합성한 소리, 원곡 아님). 24시간이 지나면 없음. */
    fun audio(part: String?): File? = if (audioAvailable()) mp3(part) ?: midi(part) else null

    val generated: Set<String> get() = result.generatedParts.toSet()

    /** 소리가 거의 없어서 경고를 보여줄 파트 (서버 이름: piano, guitar, bass, drums) */
    val faint: Set<String> get() = result.faintParts.toSet()

    /** 원곡에 기타가 없어서 기타 2대를 골랐어도 1대만 만든 결과 */
    val oneGuitarOnly: Boolean get() = result.guitarsDelivered == 1

    private fun file(rel: String?): File? = rel?.let { File(dir, it) }?.takeIf { it.isFile }
}

object ScoreStore {
    private const val RESULT = "result.json"
    private const val ACTIVE = "active_semitones.txt"

    fun dir(ctx: Context, workId: Long) = File(ctx.filesDir, "scores/$workId")

    /** 듣기용 MP3를 두는 시간. 서버(ROCKY_AUDIO_TTL_SEC)와 같게. */
    const val AUDIO_TTL_MS = 24L * 60 * 60 * 1000

    fun load(ctx: Context, workId: Long): LocalScore? {
        val root = dir(ctx, workId)
        val offset = File(root, ACTIVE).takeIf { it.isFile }?.readText()?.trim()?.toIntOrNull()
            ?.takeIf { it in -12..12 } ?: 0
        val selected = if (offset == 0) root else variantDir(root, offset)
        val json = File(selected, RESULT).takeIf { it.isFile } ?: File(root, RESULT).takeIf { it.isFile }
            ?: return null
        return runCatching {
            val result = ApiJson.result(json.readText())
            val until = audioUntil(root, result)
            // 듣기 기간이 지났으면 폰에 받아 둔 MP3도 지운다 (악보·MIDI는 그대로).
            if (System.currentTimeMillis() >= until) dropAudio(root)
            LocalScore(json.parentFile!!, result, if (json.parentFile == root) 0 else offset, until)
        }.getOrNull()
    }

    /** 서버가 알려 준 만료 시각. 예전 서버에서 받은 곡은 원본 결과를 받은 때부터 24시간. */
    internal fun audioUntil(root: File, result: JobResult): Long {
        result.audioExpiresAt?.let { return it }
        val original = File(root, RESULT)
        val fromOriginal = if (original.isFile) runCatching { ApiJson.result(original.readText()).audioExpiresAt }.getOrNull() else null
        return fromOriginal ?: (original.takeIf { it.isFile }?.lastModified() ?: System.currentTimeMillis()) + AUDIO_TTL_MS
    }

    /** 이 곡 폴더의 MP3를 모두 지운다 (원키와 바꾼 키 모두). */
    internal fun dropAudio(root: File) {
        root.walkTopDown().filter { it.isFile && it.extension.equals("mp3", ignoreCase = true) }.forEach { it.delete() }
    }

    private fun variantDir(root: File, semitones: Int) =
        File(root, "transpositions/${if (semitones > 0) "+" else ""}$semitones")

    fun useOriginal(ctx: Context, workId: Long): LocalScore {
        val root = dir(ctx, workId)
        val original = File(root, RESULT)
        require(original.isFile) { "원본 악보가 없어요" }
        File(root, ACTIVE).writeText("0")
        val result = ApiJson.result(original.readText())
        return LocalScore(root, result, 0, audioUntil(root, result))
    }

    /** Download every band/part PDF, MIDI and MP3 before switching the active key. */
    fun transpose(ctx: Context, server: ScoreServer, workId: Long, semitones: Int): LocalScore {
        require(semitones in -12..12 && semitones != 0)
        val root = dir(ctx, workId)
        val original = File(root, RESULT).takeIf { it.isFile } ?: error("원본 악보가 없어요")
        val jobId = ApiJson.result(original.readText()).id
        val target = variantDir(root, semitones).apply { mkdirs() }
        val result = server.transpose(jobId, semitones)
        val paths = files(result)
        for (path in paths) {
            val dest = File(target, path)
            require(dest.canonicalPath.startsWith(target.canonicalPath + File.separator)) { "잘못된 결과 경로" }
            if (!dest.isFile) server.downloadTransposed(jobId, semitones, path, dest)
        }
        File(target, RESULT).writeText(toJson(result))
        File(root, ACTIVE).writeText(semitones.toString())
        return LocalScore(target, result, semitones, audioUntil(root, result))
    }

    /** 결과 PDF·MIDI를 모두 받아 저장한다. 네트워크를 쓰므로 IO 스레드에서. */
    fun download(ctx: Context, server: ScoreServer, jobId: String, workId: Long): LocalScore {
        val result = server.result(jobId)
        val d = dir(ctx, workId).apply { mkdirs() }
        for (path in files(result)) {
            val dest = File(d, path)
            require(dest.canonicalPath.startsWith(d.canonicalPath + File.separator)) { "잘못된 결과 경로" }
            server.download(jobId, path, dest)
        }
        // result.json은 마지막에 써서, 이 파일이 있으면 받기가 끝난 것으로 본다.
        File(d, RESULT).writeText(toJson(result))
        return LocalScore(d, result, 0, audioUntil(d, result))
    }

    /** 결과에 들어 있는 받을 파일 (PDF, MIDI, MP3, 마디 위치). */
    private fun files(result: JobResult): Set<String> = buildSet {
        for (p in listOf(result.fullBand) + result.instruments.values) {
            add(p.pdf); p.midi?.let(::add); p.mp3?.let(::add); p.measures?.let(::add)
        }
    }

    /** 폰에 저장하는 result.json. [ApiJson.result]로 다시 읽는다. */
    internal fun toJson(r: JobResult): String {
        fun part(p: ScorePart) = org.json.JSONObject().put("pdf", p.pdf).put("midi", p.midi ?: org.json.JSONObject.NULL)
            .put("pages", p.pages ?: org.json.JSONObject.NULL).put("mp3", p.mp3 ?: org.json.JSONObject.NULL)
            .put("measures", p.measures ?: org.json.JSONObject.NULL)
        val inst = org.json.JSONObject()
        r.instruments.forEach { (k, v) -> inst.put(k, part(v)) }
        return org.json.JSONObject()
            .put("id", r.id).put("title", r.title)
            .put("full_band", part(r.fullBand)).put("instruments", inst)
            .put("original_parts", org.json.JSONArray(r.originalParts))
            .put("generated_parts", org.json.JSONArray(r.generatedParts))
            .put("faint_parts", org.json.JSONArray(r.faintParts))
            .put("guitars_delivered", r.guitarsDelivered ?: org.json.JSONObject.NULL)
            .put("audio_expires_at", r.audioExpiresAt?.let { it / 1000.0 } ?: org.json.JSONObject.NULL)
            .toString()
    }
}
