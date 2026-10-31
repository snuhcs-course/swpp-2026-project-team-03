// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.progress

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
enum class Stage(val title: String, val desc: String, val weight: Float) {
    SEPARATE("음원 분리 중", "보컬을 빼고 악기 소리만 남기고 있어요", 0.10f),
    TRANSCRIBE("채보 중", "음원에서 악기별 음을 찾고 있어요", 0.75f),
    BEATS("박자 맞추는 중", "박과 마디 위치를 찾고 있어요", 0.05f),
    ARRANGE("밴드 편곡 중", "고른 악기로 악보를 만들고 있어요", 0.10f),
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
}

/** "약 1분 30초 남음"처럼 사람이 읽기 좋게. 짧게 끝나는 숫자 변화에 흔들리지 않도록 반올림한다. */
fun formatEta(sec: Int?): String = when {
    sec == null -> "남은 시간 계산 중"
    sec <= 5 -> "곧 끝나요"
    sec < 60 -> "약 ${roundTo(sec, 5)}초 남음"
    else -> {
        val rounded = roundTo(sec, 10)
        val m = rounded / 60
        val s = rounded % 60
        if (s == 0) "약 ${m}분 남음" else "약 ${m}분 ${s}초 남음"
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
