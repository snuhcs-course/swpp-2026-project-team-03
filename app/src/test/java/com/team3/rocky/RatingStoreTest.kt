// AI-generated with Claude Code, 2026-11-09
package com.team3.rocky

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** 악보 별점을 저장했다 다시 읽을 때 내용이 그대로인지 */
class RatingStoreTest {
    @Test fun keepsEverythingWhenSavedAndReadBack() {
        val r = RatingStore.Rating(7L, "Basket\tCase", listOf("drums", "guitar"), 4, 1_700_000_000_000L)
        val back = RatingStore.decode(7L, RatingStore.encode(r))!!
        assertEquals(4, back.stars)
        assertEquals("Basket Case", back.title)
        assertEquals(listOf("drums", "guitar"), back.instruments)
        assertEquals(1_700_000_000_000L, back.ratedAt)
        assertEquals(false, back.sent)
    }

    @Test fun ignoresBrokenOrOutOfRangeValues() {
        assertNull(RatingStore.decode(1L, "garbage"))
        assertNull(RatingStore.decode(1L, "9\t0\t0\tdrums\tSong"))
    }
}
