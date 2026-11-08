// AI-generated with Claude Code, 2026-11-01
package com.team3.rocky.server

import com.team3.rocky.progress.JobProgress
import com.team3.rocky.progress.Stage
import org.json.JSONObject

/** GET /jobs/{id} 응답 (server/README.md 참고). */
data class JobStatus(
    val id: String,
    /** queued, running, publishing, cancelling, cancelled, complete, failed */
    val state: String,
    val stage: Stage,
    val completed: Int,
    val total: Int,
    val etaSec: Int?,
    val queuePosition: Int?,
    val error: String?,
    /** 기다리는 이유 등 서버가 보내는 짧은 안내 (예: "GPU 차례를 기다리는 중") */
    val note: String? = null,
    /**
     * 파이프라인이 입력을 거부했을 때만 있다 (state는 failed): too_short, silent, not_band_audio.
     * 이때 error는 사용자에게 바로 보여줄 수 있는 안내 문장이다.
     */
    val reason: String? = null,
) {
    val isRejected get() = isFailed && reason != null

    val isDone get() = state == "complete"
    val isFailed get() = state == "failed"
    val isCancelled get() = state == "cancelled"

    fun toProgress() = JobProgress(stage, completed, total, etaSec, done = isDone)
}

/** 결과 파일 하나 묶음: PDF 악보, MIDI, 재생용 MP3. 경로는 서버의 작업 폴더 기준 상대 경로. */
data class ScorePart(val pdf: String, val midi: String?, val pages: Int?, val mp3: String? = null)

/** GET /jobs/{id}/result 응답. */
data class JobResult(
    val id: String,
    val title: String,
    val fullBand: ScorePart,
    /** piano, guitar, bass, drums (+ AI가 기타를 하나 더 만들면 guitar_1, guitar_2) 중 결과에 있는 것 */
    val instruments: Map<String, ScorePart>,
    val originalParts: List<String>,
    /** 원곡에 없어서 MIDI-GPT가 새로 만든 악기 → 결과 화면에 'AI 생성' 표시 */
    val generatedParts: List<String>,
    /**
     * 사용자가 원곡에 있다고 골랐지만 그 악기 소리가 거의 들리지 않은 파트 (piano, guitar, bass, drums).
     * 악보는 만들어졌지만 비어 있거나 부정확할 수 있다 → 결과 화면에 경고 표시용.
     */
    val faintParts: List<String> = emptyList(),
)

object ApiJson {
    fun status(text: String): JobStatus {
        val o = JSONObject(text)
        return JobStatus(
            id = o.getString("id"),
            state = o.getString("state"),
            stage = Stage.entries.firstOrNull { it.name == o.optString("stage") } ?: Stage.SEPARATE,
            completed = o.optInt("completed", 0),
            total = o.optInt("total", 0),
            etaSec = o.intOrNull("eta_sec"),
            queuePosition = o.intOrNull("queue_position"),
            error = o.stringOrNull("error"),
            note = o.stringOrNull("note"),
            reason = o.stringOrNull("reason"),
        )
    }

    fun result(text: String): JobResult {
        val o = JSONObject(text)
        val inst = o.getJSONObject("instruments")
        return JobResult(
            id = o.getString("id"),
            title = o.optString("title"),
            fullBand = part(o.getJSONObject("full_band")),
            instruments = inst.keys().asSequence().associateWith { part(inst.getJSONObject(it)) },
            originalParts = o.strings("original_parts"),
            generatedParts = o.strings("generated_parts"),
            faintParts = o.strings("faint_parts"),
        )
    }

    fun jobId(text: String): String = JSONObject(text).getString("id")
    fun jobState(text: String): String = JSONObject(text).getString("state")

    private fun part(o: JSONObject) =
        ScorePart(o.getString("pdf"), o.stringOrNull("midi"), o.intOrNull("pages"), o.stringOrNull("mp3"))

    private fun JSONObject.intOrNull(key: String) = if (has(key) && !isNull(key)) getInt(key) else null
    private fun JSONObject.stringOrNull(key: String) = if (has(key) && !isNull(key)) getString(key) else null
    private fun JSONObject.strings(key: String): List<String> {
        val a = optJSONArray(key) ?: return emptyList()
        return (0 until a.length()).map { a.getString(it) }
    }
}
