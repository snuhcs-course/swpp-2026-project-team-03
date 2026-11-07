// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.progress

import com.team3.rocky.tr
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlin.math.ceil
import kotlin.math.roundToInt

/**
 * 악보를 만드는 단계. weight는 전체 시간에서 차지하는 비율로,
 * A100에서 MuScriptor large로 Immigrant Song(2분 27초)을 돌린 기록을 기준으로 잡았다.
 * 채보가 거의 대부분(156초)을 차지한다.
 */
enum class Stage(
    private val ko: String,
    private val en: String,
    private val koDesc: String,
    private val enDesc: String,
    val weight: Float,
) {
    // 사용자가 보는 이름이라 '음원 분리·채보' 같은 우리 쪽 용어 대신 하는 일을 그대로 적는다.
    SEPARATE("악기 소리 나누는 중", "Separating instruments", "곡에서 악기별 소리를 따로 꺼내고 있어요", "Pulling each instrument out of the song", 0.10f),
    TRANSCRIBE("악보로 옮기는 중", "Writing the notes", "악기마다 연주한 음을 악보에 적고 있어요", "Writing down what each instrument plays", 0.75f),
    BEATS("박자 맞추는 중", "Lining up the beat", "마디와 박자를 맞추고 있어요", "Matching bars and beats", 0.05f),
    ARRANGE("우리 밴드 악보 완성 중", "Finishing your band's scores", "우리 밴드에 없는 파트까지 채우고 있어요", "Filling in the parts your band needs", 0.10f);

    val title get() = tr(ko, en)
    val desc get() = tr(koDesc, enDesc)

    /** 1부터 세는 단계 번호 */
    val index get() = ordinal + 1
}

/**
 * 서버가 보내줄 진행 상태 한 건.
 * 채보 단계의 completed/total은 MuScriptor가 처리한 5초 구간 수다
 * (ml/pipeline/transcribe_with_progress.py가 쓰는 progress.jsonl과 같은 값).
 */
data class JobProgress(
    val stage: Stage,
    val completed: Int,
    val total: Int,
    /** 작업 전체가 끝날 때까지 남은 시간(초). 아직 모르면 null. */
    val etaSec: Int?,
    val done: Boolean = false,
) {
    val stageFraction: Float
        get() = if (done) 1f else if (total <= 0) 0f else (completed.toFloat() / total).coerceIn(0f, 1f)

    /** 0~1. 앞 단계들의 비율을 더하고, 지금 단계는 진행한 만큼만 더한다. */
    val overall: Float
        get() = if (done) 1f else Stage.entries
            .takeWhile { it != stage }
            .fold(0f) { acc, s -> acc + s.weight } + stage.weight * stageFraction

    /** 지금 단계가 끝나는 지점(0~1). 서버가 다음 단계를 알려주기 전에는 진행 막대가 이 앞에서 멈춘다. */
    val stageEnd: Float
        get() = Stage.entries.takeWhile { it != stage }.fold(0f) { acc, s -> acc + s.weight } + stage.weight
}

/** "약 1분 30초 남음"처럼 사람이 읽기 좋게. 짧게 끝나는 숫자 변화에 흔들리지 않도록 반올림한다. */
fun formatEta(sec: Int?): String = when {
    sec == null -> tr("남은 시간 계산 중", "Estimating time")
    sec <= 5 -> tr("곧 끝나요", "Almost done")
    sec < 60 -> tr("약 ${roundTo(sec, 5)}초 남음", "About ${roundTo(sec, 5)} sec left")
    else -> {
        val rounded = roundTo(sec, 10)
        val m = rounded / 60
        val s = rounded % 60
        if (s == 0) tr("약 ${m}분 남음", "About $m min left")
        else tr("약 ${m}분 ${s}초 남음", "About $m min $s sec left")
    }
}

private fun roundTo(value: Int, step: Int) = ((value.toFloat() / step).roundToInt() * step).coerceAtLeast(step)

/** 진행 상태를 받아오는 곳. 서버가 생기면 GET /jobs/{id}를 2초마다 부르는 구현으로 바꾼다. */
interface ProgressSource {
    fun track(jobId: String): Flow<JobProgress>
}

/**
 * 시연용: 서버 없이 진행 상태를 흉내 낸다.
 * 실제 데모 곡처럼 채보를 30개 구간으로 나눠 보내되, 시간은 10초 남짓으로 줄였다.
 */
object DemoProgress : ProgressSource {
    private data class Step(val stage: Stage, val units: Int, val msPerUnit: Long)

    private val plan = listOf(
        Step(Stage.SEPARATE, 4, 300),
        Step(Stage.TRANSCRIBE, 30, 250),
        Step(Stage.BEATS, 1, 600),
        Step(Stage.ARRANGE, 2, 500),
    )

    override fun track(jobId: String): Flow<JobProgress> = flow {
        val totalMs = plan.sumOf { it.units * it.msPerUnit }
        var elapsed = 0L
        for (step in plan) {
            for (i in 0..step.units) {
                // 실제 채보처럼 첫 구간이 끝나기 전에는 남은 시간을 모른다.
                val eta = if (step.stage == Stage.TRANSCRIBE && i == 0) null
                else ceil((totalMs - elapsed) / 1000.0).toInt()
                emit(JobProgress(step.stage, i, step.units, eta))
                if (i < step.units) {
                    delay(step.msPerUnit)
                    elapsed += step.msPerUnit
                }
            }
        }
        emit(JobProgress(Stage.ARRANGE, 1, 1, 0, done = true))
    }
}
