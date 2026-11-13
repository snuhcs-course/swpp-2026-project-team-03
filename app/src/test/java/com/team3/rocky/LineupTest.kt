// AI-generated with Claude Code, 2026-11-03
package com.team3.rocky

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LineupTest {
    @Test fun guitarTileTogglesAndStepperSetsCount() {
        var s = Demo.toggleLineup(emptySet(), "guitar"); assertEquals(1, Demo.guitarCount(s))
        s = Demo.setGuitarCount(s, 2); assertEquals(2, Demo.guitarCount(s))
        s = Demo.setGuitarCount(s, 1); assertEquals(setOf("guitar"), s)
        s = Demo.setGuitarCount(s, 2)
        // 2대일 때 칸을 누르면 기타를 모두 뺀다.
        assertEquals(emptySet<String>(), Demo.toggleLineup(s, "guitar"))
    }

    @Test fun otherInstrumentsToggleOnOff() {
        val on = Demo.toggleLineup(setOf("bass"), "piano")
        assertEquals(setOf("bass", "piano"), on)
        assertEquals(setOf("bass"), Demo.toggleLineup(on, "piano"))
    }

    @Test fun lineupFromBandMembersSkipsVocalAndCountsGuitars() {
        assertEquals(setOf("drums", "guitar", Demo.GUITAR2), Demo.lineupOf(listOf("vocal", "guitar", "drums", "guitar")))
        assertEquals(setOf("bass", "guitar"), Demo.lineupOf(listOf("guitar", "bass")))
    }

    @Test fun aiGeneratedIsWhatOriginalLacks() {
        val lineup = listOf("piano", "drums", "bass", "guitar", Demo.GUITAR2)
        assertEquals(setOf("piano", Demo.GUITAR2), Demo.aiGenerated(lineup, listOf("drums", "bass", "guitar")))
        // 원곡 구성을 모르는 예전 작업은 데모 곡 기준(피아노)으로 본다.
        assertEquals(setOf("piano"), Demo.aiGenerated(listOf("piano", "drums"), emptyList()))
    }

    @Test fun labelsNumberGuitarsOnlyWhenTwo() {
        assertEquals("피아노 · 기타", Demo.labels(listOf("piano", "guitar")))
        assertEquals("기타 1 · 기타 2", Demo.labels(listOf("guitar", Demo.GUITAR2)))
        assertEquals("guitar", Demo.assetBase(Demo.GUITAR2))
    }

    @Test fun orderedFollowsScoreOrder() =
        assertEquals(listOf("piano", "bass", "guitar", Demo.GUITAR2), Demo.ordered(setOf(Demo.GUITAR2, "bass", "guitar", "piano")))

    // ----- 기타 대수 바꿔서 다시 만들기 -----

    @Test fun redoKeepsWhatTheModelFoundAndUsesTheChosenGuitarCount() {
        val found = listOf("bass", "drums", "guitar", "guitar2")
        assertEquals(listOf("drums", "bass", "guitar"), Demo.redoOriginal(found, 1))
        assertEquals(listOf("drums", "bass"), Demo.redoOriginal(found, 0))
        assertEquals(listOf("piano", "drums", "guitar", "guitar2"), Demo.redoOriginal(listOf("piano", "drums"), 2))
    }

    @Test fun redoIgnoresNamesTheAppDoesNotKnow() {
        assertEquals(listOf("guitar"), Demo.redoOriginal(listOf("vocals", "other"), 1))
    }

    // ----- 개인 연습용 기타 안내 -----

    @Test fun soloGuitarNoteDependsOnTheCount() {
        assertEquals(null, Demo.personalGuitarNote(0))
        assertTrue(Demo.personalGuitarNote(1)!!.contains("두 기타가 한 악보로 합쳐져"))
        assertTrue(Demo.personalGuitarNote(2)!!.contains("AI가 새로 만들어요"))
    }
}
