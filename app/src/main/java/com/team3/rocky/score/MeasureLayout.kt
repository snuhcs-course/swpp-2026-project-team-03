package com.team3.rocky.score

import kotlin.math.abs

/** 마디 하나가 그려진 곳 (페이지 번호와 그 페이지 그림의 픽셀 좌표). */
data class MeasureBox(val page: Int, val top: Int, val bottom: Int, val left: Int, val right: Int)

/** 악보 전체의 마디 위치. [exact]가 false면 마디선을 못 읽어, 마디마다 그 마디가 있을 줄 전체를 가리킨다. */
class MeasureLayout(val boxes: List<MeasureBox>, val exact: Boolean) {
    val count get() = boxes.size

    /** [measure]번째(0부터) 마디. 범위를 넘으면 가장 가까운 마디. */
    fun box(measure: Int): MeasureBox? = boxes.getOrNull(measure.coerceIn(0, (count - 1).coerceAtLeast(0)))

    companion object {
        /**
         * @param pages 페이지마다 [ScoreLayout.systems]의 결과
         * @param measures MIDI로 센 마디 수. 모르면 null
         */
        fun build(pages: List<List<StaffSystem>>, measures: Int?): MeasureLayout {
            val systems = pages.flatMapIndexed { p, list -> list.map { p to it } }
            if (systems.isEmpty()) return MeasureLayout(emptyList(), exact = false)

            val detected = systems.flatMap { (p, s) ->
                val lefts = listOf(s.left) + s.bars.dropLast(1)
                s.bars.indices.map { i -> MeasureBox(p, s.top, s.bottom, lefts[i], s.bars[i]) }
            }
            // 마디선으로 센 수가 MIDI와 같으면(끝의 빈 마디 하나 차이까지) 그대로 쓴다.
            if (detected.isNotEmpty() && (measures == null || abs(detected.size - measures) <= 1)) {
                return MeasureLayout(detected, exact = true)
            }
            if (measures == null || measures <= 0) return MeasureLayout(emptyList(), exact = false)

            // 아니면 MIDI 마디 수를 줄 길이에 비례해 나눈다 (줄마다 마디 수가 비슷하다고 본다).
            val widths = systems.map { (_, s) -> (s.right - s.left).coerceAtLeast(1).toDouble() }
            val total = widths.sum()
            val exactShares = widths.map { it / total * measures }
            val shares = exactShares.map { it.toInt() }.toMutableList()
            exactShares.indices.sortedByDescending { exactShares[it] - shares[it] }
                .take(measures - shares.sum()).forEach { shares[it]++ }
            // 마디 경계를 모르므로 줄 전체를 그 줄의 마디들 위치로 쓴다 (틀린 마디에 칠하지 않게).
            val boxes = systems.flatMapIndexed { i, (p, s) ->
                List(shares[i]) { MeasureBox(p, s.top, s.bottom, s.left, s.right) }
            }
            return MeasureLayout(boxes, exact = false)
        }
    }
}
