// AI-generated with Claude Code, 2026-11-07
package com.team3.rocky.progress

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** 진행 막대가 멈췄다 뛰지 않고 일정하게 올라가는지 */
class SmoothProgressTest {
    private fun at(stage: Stage, done: Int, total: Int, eta: Int?) = JobProgress(stage, done, total, eta)

    @Test fun movesSteadilyWhileTheServerValueStaysTheSame() {
        val bar = SmoothProgress()
        val p = at(Stage.SEPARATE, 0, 0, 300)          // 서버는 0%에서 한참 머문다
        val first = bar.step(p, 1f)
        val second = bar.step(p, 1f)
        assertTrue(first > 0f)
        assertEquals(first, second - first, 0.0005f)   // 같은 시간에 같은 만큼
    }

    @Test fun waitsBeforeTheEndOfTheCurrentStage() {
        val bar = SmoothProgress()
        val p = at(Stage.SEPARATE, 0, 0, 10)
        repeat(600) { bar.step(p, 1f) }
        assertTrue(bar.shown < Stage.SEPARATE.weight)  // 다음 단계 소식 전에는 10%를 넘지 않는다
    }

    @Test fun catchesUpWithoutJumpingAndNeverGoesBack() {
        val bar = SmoothProgress()
        bar.step(at(Stage.TRANSCRIBE, 10, 20, 60), 0.1f)   // 실제는 47.5%
        assertTrue(bar.shown < 0.1f)                        // 한 번에 뛰지 않는다
        repeat(100) { bar.step(at(Stage.TRANSCRIBE, 10, 20, 60), 0.1f) }
        val caught = bar.shown
        assertTrue(caught >= 0.475f)                        // 10초 안에 따라잡는다
        bar.step(at(Stage.SEPARATE, 0, 0, 60), 0.1f)        // 서버 값이 뒤로 가도
        assertTrue(bar.shown >= caught)                     // 막대는 뒤로 가지 않는다
    }

    @Test fun onlyDoneShowsHundred() {
        val bar = SmoothProgress()
        repeat(1000) { bar.step(at(Stage.ARRANGE, 1, 1, 0), 1f) }
        assertTrue(bar.shown <= 0.99f)
        assertEquals(1f, bar.step(JobProgress(Stage.ARRANGE, 1, 1, 0, done = true), 0.1f), 0f)
    }

    @Test fun showsOnePercentAsSoonAsTheSongIsUploaded() {
        val bar = SmoothProgress()
        assertEquals(0, (bar.step(null, 5f) * 100).toInt())
        bar.started()
        // 서버의 첫 진행 상태가 오기 전에도 1%
        assertEquals(1, (bar.step(null, 5f) * 100).toInt())
        // 다시 불러도 이미 앞서 있으면 뒤로 가지 않는다
        repeat(100) { bar.step(at(Stage.SEPARATE, 5, 10, 300), 1f) }
        val before = bar.shown
        bar.started()
        assertEquals(before, bar.shown, 0f)
    }
}
