package com.team3.rocky

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** U1–U4: 보관함 저장 형식 (순수 로직, 에뮬레이터 불필요) */
class WorkCodecTest {

    private val w1 = Work(1L, "Time-Bomb", listOf("piano", "guitar"), "2026.10.21 14:00")
    private val w2 = Work(2L, "21 Guns", listOf("bass"), "2026.10.21 15:00")

    // U1
    @Test
    fun encodeThenDecode_returnsSameWorks() {
        val decoded = WorkCodec.decode(WorkCodec.encode(listOf(w1, w2)))
        assertEquals(listOf(w1, w2), decoded)
    }

    @Test
    fun emptyInstrumentList_survivesRoundTrip() {
        val w = Work(3L, "No inst", emptyList(), "2026.10.21")
        assertEquals(listOf(w), WorkCodec.decode(WorkCodec.encode(listOf(w))))
    }

    // U2
    @Test
    fun upsert_sameId_keepsOneEntryAtTop() {
        val updated = w1.copy(title = "Time-Bomb (v2)")
        val result = WorkCodec.upsert(listOf(w2, w1), updated)
        assertEquals(listOf(updated, w2), result)
    }

    @Test
    fun upsert_newId_addsToTop() {
        assertEquals(listOf(w2, w1), WorkCodec.upsert(listOf(w1), w2))
    }

    // U3
    @Test
    fun titleWithTabOrNewline_doesNotBreakFormat() {
        val tricky = Work(4L, "Sweet\tChild\nO' Mine\r", listOf("piano"), "2026.10.21")
        val decoded = WorkCodec.decode(WorkCodec.encode(listOf(tricky, w2)))
        assertEquals(2, decoded.size)
        assertEquals("Sweet Child O' Mine ", decoded[0].title)
        assertEquals(listOf("piano"), decoded[0].instruments)
        assertEquals(w2, decoded[1])
    }

    // U4
    @Test
    fun nullOrBlank_returnsEmptyList() {
        assertTrue(WorkCodec.decode(null).isEmpty())
        assertTrue(WorkCodec.decode("").isEmpty())
        assertTrue(WorkCodec.decode("  \n \n").isEmpty())
    }

    @Test
    fun malformedLines_areSkipped() {
        val raw = listOf(
            "garbage",                                   // 칸 부족
            "abc\tBad id\tpiano\t2026.10.21",            // id가 숫자가 아님
            WorkCodec.encode(listOf(w1)),                // 정상
            "5\tToo short",                              // 칸 부족
        ).joinToString("\n")
        assertEquals(listOf(w1), WorkCodec.decode(raw))
    }

    // U8 (Iteration 2 추가): 회원별 보관함 칸
    @Test
    fun workKey_separatesUsers() {
        assertEquals("works_7", workKey(7L))
        assertEquals("works_guest", workKey(null))
        assertTrue(workKey(1L) != workKey(2L))
    }
}
