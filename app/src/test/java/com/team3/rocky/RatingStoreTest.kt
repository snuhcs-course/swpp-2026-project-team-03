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

    @Test fun keepsTheOneLineComment() {
        val r = RatingStore.Rating(7L, "Song", listOf("bass"), 3, 1L, comment = "베이스가\t좀\n틀려요")
        val back = RatingStore.decode(7L, RatingStore.encode(r))!!
        assertEquals("베이스가 좀 틀려요", back.comment)
        assertEquals("Song", back.title)
    }

    @Test fun readsRatingsSavedBeforeComments() {
        val old = RatingStore.decode(3L, "5\t10\t1\tdrums,guitar\tBasket Case")!!
        assertEquals(5, old.stars)
        assertEquals("Basket Case", old.title)
        assertEquals("", old.comment)
        assertEquals(true, old.sent)
    }

    @Test fun commentIsOneLineAndCapped() {
        assertEquals("a b", RatingStore.cleanComment("  a\n\n b  "))
        assertEquals(RatingStore.COMMENT_MAX, RatingStore.cleanComment("가".repeat(150)).length)
    }

    @Test fun ignoresBrokenOrOutOfRangeValues() {
        assertNull(RatingStore.decode(1L, "garbage"))
        assertNull(RatingStore.decode(1L, "9\t0\t0\tdrums\tSong"))
    }
}
