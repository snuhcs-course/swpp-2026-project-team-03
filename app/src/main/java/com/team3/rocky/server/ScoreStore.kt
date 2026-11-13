// AI-generated with Claude Code, 2026-11-01
package com.team3.rocky.server

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import java.io.File

/**
 * 서버에서 받은 결과를 폰에 저장해 둔 것. 폴더는 filesDir/scores/<작업 id>/.
 * 작업 id(Work.id)로 찾는다. 다른 밴드원이 공유한 악보는 처음 열 때 서버에서 받아 여기에 둔다.
 * 폴더가 없는 작업은 악보 파일이 없는 것으로 본다.
 */
class LocalScore(val dir: File, val result: JobResult, val semitones: Int = 0) {
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
    fun mp3(part: String?): File? = file(entry(part)?.mp3)

    /** 재생할 파일: MP3가 있으면 MP3, 없으면 MIDI (둘 다 악보로 합성한 소리, 원곡 아님). */
    fun audio(part: String?): File? = mp3(part) ?: midi(part)

    val generated: Set<String> get() = result.generatedParts.toSet()

    /** 소리가 거의 없어서 경고를 보여줄 파트 (서버 이름: piano, guitar, bass, drums) */
    val faint: Set<String> get() = result.faintParts.toSet()

    private fun file(rel: String?): File? = rel?.let { File(dir, it) }?.takeIf { it.isFile }
}

object ScoreStore {
    private const val RESULT = "result.json"
    private const val ACTIVE = "active_semitones.txt"

    fun dir(ctx: Context, workId: Long) = File(ctx.filesDir, "scores/$workId")

    fun load(ctx: Context, workId: Long): LocalScore? {
        val root = dir(ctx, workId)
        val offset = File(root, ACTIVE).takeIf { it.isFile }?.readText()?.trim()?.toIntOrNull()
            ?.takeIf { it in -12..12 } ?: 0
        val selected = if (offset == 0) root else variantDir(root, offset)
        val json = File(selected, RESULT).takeIf { it.isFile } ?: File(root, RESULT).takeIf { it.isFile }
            ?: return null
        return runCatching {
            LocalScore(json.parentFile!!, ApiJson.result(json.readText()),
                if (json.parentFile == root) 0 else offset)
        }.getOrNull()
    }

    private fun variantDir(root: File, semitones: Int) =
        File(root, "transpositions/${if (semitones > 0) "+" else ""}$semitones")

    fun useOriginal(ctx: Context, workId: Long): LocalScore {
        val root = dir(ctx, workId)
        val original = File(root, RESULT)
        require(original.isFile) { "원본 악보가 없어요" }
        File(root, ACTIVE).writeText("0")
        return LocalScore(root, ApiJson.result(original.readText()))
    }

    /** Download every band/part PDF, MIDI and MP3 before switching the active key. */
    fun transpose(ctx: Context, server: ScoreServer, workId: Long, semitones: Int): LocalScore {
        require(semitones in -12..12 && semitones != 0)
        val root = dir(ctx, workId)
        val original = File(root, RESULT).takeIf { it.isFile } ?: error("원본 악보가 없어요")
        val jobId = ApiJson.result(original.readText()).id
        val target = variantDir(root, semitones).apply { mkdirs() }
        val result = server.transpose(jobId, semitones)
        val paths = buildSet {
            for (p in listOf(result.fullBand) + result.instruments.values) {
                add(p.pdf); p.midi?.let(::add); p.mp3?.let(::add)
            }
        }
        for (path in paths) {
            val dest = File(target, path)
            require(dest.canonicalPath.startsWith(target.canonicalPath + File.separator)) { "잘못된 결과 경로" }
            if (!dest.isFile) server.downloadTransposed(jobId, semitones, path, dest)
        }
        File(target, RESULT).writeText(toJson(result))
        File(root, ACTIVE).writeText(semitones.toString())
        return LocalScore(target, result, semitones)
    }

    /** 결과 PDF·MIDI를 모두 받아 저장한다. 네트워크를 쓰므로 IO 스레드에서. */
    fun download(ctx: Context, server: ScoreServer, jobId: String, workId: Long): LocalScore {
        val result = server.result(jobId)
        val d = dir(ctx, workId).apply { mkdirs() }
        val paths = buildSet {
            for (p in listOf(result.fullBand) + result.instruments.values) {
                add(p.pdf); p.midi?.let(::add); p.mp3?.let(::add)
            }
        }
        for (path in paths) server.download(jobId, path, File(d, path))
        // result.json은 마지막에 써서, 이 파일이 있으면 받기가 끝난 것으로 본다.
        File(d, RESULT).writeText(toJson(result))
        return LocalScore(d, result)
    }

    private fun toJson(r: JobResult): String {
        fun part(p: ScorePart) = org.json.JSONObject().put("pdf", p.pdf).put("midi", p.midi ?: org.json.JSONObject.NULL)
            .put("pages", p.pages ?: org.json.JSONObject.NULL).put("mp3", p.mp3 ?: org.json.JSONObject.NULL)
        val inst = org.json.JSONObject()
        r.instruments.forEach { (k, v) -> inst.put(k, part(v)) }
        return org.json.JSONObject()
            .put("id", r.id).put("title", r.title)
            .put("full_band", part(r.fullBand)).put("instruments", inst)
            .put("original_parts", org.json.JSONArray(r.originalParts))
            .put("generated_parts", org.json.JSONArray(r.generatedParts))
            .put("faint_parts", org.json.JSONArray(r.faintParts))
            .toString()
    }
}

/** PDF 악보를 화면 너비에 맞춘 그림으로 바꾼다. 페이지가 많으면 오래 걸리니 IO 스레드에서. */
object PdfPages {
    fun render(file: File, widthPx: Int, maxPages: Int = 30): List<Bitmap> =
        ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { fd ->
            PdfRenderer(fd).use { pdf ->
                (0 until minOf(pdf.pageCount, maxPages)).map { i ->
                    pdf.openPage(i).use { page ->
                        val h = (widthPx.toFloat() * page.height / page.width).toInt().coerceAtLeast(1)
                        Bitmap.createBitmap(widthPx, h, Bitmap.Config.ARGB_8888).also { bmp ->
                            bmp.eraseColor(Color.WHITE)
                            page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        }
                    }
                }
            }
        }
}
