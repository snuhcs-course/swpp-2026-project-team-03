// AI-generated with Claude Code, 2026-11-07
package com.team3.rocky.progress

import kotlin.math.max
import kotlin.math.min

/**
 * 화면에 보여줄 진행률을 일정한 속도로 올린다.
 *
 * 서버는 2초마다, 그것도 단계가 바뀔 때 크게 뛰는 값을 준다(음원 분리 0% → 10%처럼).
 * 그대로 보여주면 한참 멈췄다가 갑자기 뛰어서 멈춘 것처럼 보인다. 그래서
 * - 평소에는 남은 시간(eta)에 맞춰 남은 비율을 고르게 나눠 조금씩 올리고,
 * - 실제 값이 더 앞서 있으면 [catchUpSec]초 안에 따라잡고,
 * - 서버가 다음 단계를 알려주기 전에는 지금 단계의 끝([JobProgress.stageEnd]) 바로 앞에서 기다리고,
 * - 절대 뒤로 가지 않으며, 끝났다는 값이 와야 100%가 된다.
 */
class SmoothProgress(
    /** 남은 시간을 모를 때 0%에서 100%까지 걸린다고 볼 시간(초) */
    private val fallbackSec: Float = 360f,
    private val catchUpSec: Float = 3f,
    /** 따라잡을 때 가장 느린 속도 (초당 5%) */
    private val minCatchUp: Float = 0.05f,
) {
    var shown = 0f
        private set

    /** 처음부터 다시 만들 때 0%로 되돌린다. */
    fun reset() { shown = 0f }

    /** [dtSec]초가 지났을 때 보여줄 값. */
    fun step(p: JobProgress?, dtSec: Float): Float {
        if (p == null) return shown
        if (p.done) { shown = 1f; return shown }
        val target = p.overall
        val eta = p.etaSec
        var rate = if (eta != null && eta > 0) (1f - shown).coerceAtLeast(0f) / eta else 1f / fallbackSec
        if (target > shown) rate = max(rate, max((target - shown) / catchUpSec, minCatchUp))
        // 멈춰 있을 수 있는 가장 앞: 실제 값 또는 지금 단계 끝 바로 앞. 99%는 넘지 않는다.
        val cap = min(max(target, p.stageEnd - 0.01f), 0.99f)
        shown = max(shown, min(shown + rate * dtSec, cap))
        return shown
    }
}
