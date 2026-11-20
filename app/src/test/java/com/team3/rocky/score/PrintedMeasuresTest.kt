package com.team3.rocky.score

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PrintedMeasuresTest {
    // A4 (595 x 842 pt), two measures on page 0 and one on page 1; the third measure has two boxes (two tracks).
    private val json = """
        {"version": 1, "unit": "pt", "origin": "top-left", "pages": [[595.0, 842.0], [595.0, 842.0]],
         "measures": [[[0, 115.0, 63.0, 149.5, 230.0]], [[0, 264.5, 63.0, 73.5, 230.0]],
                      [[1, 57.0, 86.0, 235.5, 95.0], [1, 57.0, 400.0, 235.5, 95.0]]]}
    """.trimIndent()

    @Test fun scalesToRenderedWidthAndMovesByTheCrop() {
        val printed = PrintedMeasures.parse(json)!!
        assertEquals(3, printed.count)
        // drawn 1190 px wide = 2 px per point; page 0 cropped 30 px from the left and 100 from the top
        val layout = printed.layout(listOf(1190, 1190), listOf(30 to 100, 0 to 0))
        assertTrue(layout.exact)
        assertEquals(MeasureBox(0, 26, 486, 200, 499), layout.box(0))
        assertEquals(MeasureBox(0, 26, 486, 499, 646), layout.box(1))
        assertEquals(MeasureBox(1, 172, 362, 114, 585), layout.box(2))  // first track's box
    }

    @Test fun measuresOnPagesThatWereNotDrawnAreLeftOut() {
        val layout = PrintedMeasures.parse(json)!!.layout(listOf(1190), listOf(0 to 0))
        assertEquals(2, layout.count)
    }

    @Test fun otherFormatsAreRejected() {
        assertNull(PrintedMeasures.parse("""{"version": 2, "unit": "pt", "pages": [], "measures": []}"""))
        assertNull(PrintedMeasures.parse("not json"))
    }
}
