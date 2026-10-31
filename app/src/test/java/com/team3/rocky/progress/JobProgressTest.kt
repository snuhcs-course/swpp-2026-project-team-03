// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.progress

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class JobProgressTest {
    private fun p(stage: Stage, completed: Int, total: Int) = JobProgress(stage, completed, total, null)

    @Test fun weightsAddUpToOne() {
        assertEquals(1f, Stage.entries.fold(0f) { acc, s -> acc + s.weight }, 1e-6f)
    }

    @Test fun overallAddsFinishedStagesAndPartOfCurrent() {
        assertEquals(0f, p(Stage.SEPARATE, 0, 4).overall, 1e-6f)
        assertEquals(0.10f, p(Stage.TRANSCRIBE, 0, 30).overall, 1e-6f)
        // 30구간 중 12구간: 0.10 + 0.75 × 0.4
        assertEquals(0.40f, p(Stage.TRANSCRIBE, 12, 30).overall, 1e-6f)
        assertEquals(0.90f, p(Stage.ARRANGE, 0, 2).overall, 1e-6f)
        assertEquals(1f, JobProgress(Stage.ARRANGE, 0, 0, 0, done = true).overall, 1e-6f)
    }

    @Test fun stageFractionIsClamped() {
        assertEquals(0f, p(Stage.TRANSCRIBE, 3, 0).stageFraction, 1e-6f)
        assertEquals(1f, p(Stage.TRANSCRIBE, 40, 30).stageFraction, 1e-6f)
    }

    @Test fun etaIsReadable() {
        assertEquals("남은 시간 계산 중", formatEta(null))
        assertEquals("곧 끝나요", formatEta(3))
        assertEquals("약 40초 남음", formatEta(38))
        assertEquals("약 1분 30초 남음", formatEta(92))
        assertEquals("약 2분 남음", formatEta(121))
    }

    @Test fun demoGoesForwardAndFinishes() = runBlocking {
        val all = DemoProgress.track("demo").toList()
        val values = all.map { it.overall }
        assertTrue(values.zipWithNext().all { (a, b) -> b >= a })
        assertTrue(all.last().done)
        // 채보 첫 구간이 끝나기 전에는 남은 시간을 모른다 (실제 MuScriptor와 같게).
        assertNull(all.first { it.stage == Stage.TRANSCRIBE }.etaSec)
        assertEquals(30, all.first { it.stage == Stage.TRANSCRIBE }.total)
    }
}
