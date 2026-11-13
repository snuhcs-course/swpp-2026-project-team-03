// AI-generated with Claude Code, 2026-11-09
package com.team3.rocky

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** 원곡에 있다고 골랐지만 원곡에서 소리가 거의 들리지 않은 파트(⚠️) 판단 */
class UnrecognizedTest {
    private val band = listOf("piano", "drums", "bass", "guitar")

    @Test fun faintPartFromTheServerIsWarned() {
        assertEquals(listOf("piano"), Demo.faintParts(band, claimed = band, faint = listOf("piano")))
    }

    @Test fun notSureMeansNoWarning() {
        assertEquals(emptyList<String>(), Demo.faintParts(band, claimed = emptyList(), faint = listOf("piano")))
    }

    @Test fun onlyPartsTheUserChoseAreWarned() {
        // 원곡 구성에서 고르지 않은 악기(AI가 만든 파트)는 ⚠️가 아니다
        assertEquals(emptyList<String>(), Demo.faintParts(band, claimed = listOf("drums", "bass"), faint = listOf("piano")))
    }

    @Test fun secondGuitarFollowsTheGuitar() {
        val lineup = listOf("drums", "guitar", "guitar2")
        assertEquals(listOf("guitar", "guitar2"), Demo.faintParts(lineup, claimed = lineup, faint = listOf("guitar")))
    }

    @Test fun warnedPartIsNotShownAsAi() {
        val w = Work(1, "t", band, "d", original = band, unrecognized = listOf("piano"))
        assertTrue(w.aiGenerated.isEmpty())
    }
}
