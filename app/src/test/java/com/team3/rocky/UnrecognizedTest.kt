// AI-generated with Claude Code, 2026-11-09
package com.team3.rocky

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** 원곡에 있다고 골랐는데 원곡에서 찾지 못한 파트(⚠️) 판단 */
class UnrecognizedTest {
    private val band = listOf("piano", "drums", "bass", "guitar")

    @Test fun claimedButNotDetectedIsWarned() {
        assertEquals(listOf("piano"), Demo.unrecognized(band, claimed = band, detected = listOf("drums", "bass", "guitar")))
    }

    @Test fun notSureMeansNoWarning() {
        assertEquals(emptyList<String>(), Demo.unrecognized(band, claimed = emptyList(), detected = listOf("drums")))
    }

    @Test fun noDetectionResultMeansNoWarning() {
        assertEquals(emptyList<String>(), Demo.unrecognized(band, claimed = band, detected = emptyList()))
    }

    @Test fun serverReportWins() {
        assertEquals(listOf("bass"), Demo.unrecognized(band, claimed = band, detected = band, reported = listOf("bass")))
    }

    @Test fun secondGuitarFollowsTheGuitar() {
        val lineup = listOf("drums", "guitar", "guitar2")
        assertEquals(listOf("guitar", "guitar2"),
            Demo.unrecognized(lineup, claimed = lineup, detected = listOf("drums")))
    }

    @Test fun warnedPartIsNotShownAsAi() {
        val w = Work(1, "t", band, "d", original = band, unrecognized = listOf("piano"))
        assertTrue(w.aiGenerated.isEmpty())
        assertFalse("piano" in w.aiGenerated)
    }
}
