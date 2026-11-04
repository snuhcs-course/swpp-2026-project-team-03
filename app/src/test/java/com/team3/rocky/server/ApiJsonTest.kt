// AI-generated with Claude Code, 2026-11-01
package com.team3.rocky.server

import com.team3.rocky.progress.Stage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** server/README.md의 응답 형식을 그대로 읽는지 확인한다. */
class ApiJsonTest {
    @Test fun runningStatusBecomesAppProgress() {
        val s = ApiJson.status(
            """{"id":"abc123abc123","title":"t","requested":["piano"],"state":"running","queue_position":null,
               "error":null,"stage":"TRANSCRIBE","completed":45,"total":120,"fraction":0.38,"eta_sec":93}"""
        )
        assertEquals(Stage.TRANSCRIBE, s.stage)
        assertEquals(93, s.etaSec)
        assertNull(s.queuePosition)
        val p = s.toProgress()
        assertEquals(0.10f + 0.75f * 45 / 120, p.overall, 1e-4f)
        assertFalse(p.done)
    }

    @Test fun queuedStatusHasNoEta() {
        val s = ApiJson.status(
            """{"id":"x","state":"queued","queue_position":2,"error":null,"stage":"SEPARATE",
               "completed":0,"total":1,"fraction":0.0,"eta_sec":null}"""
        )
        assertEquals(2, s.queuePosition)
        assertNull(s.etaSec)
    }

    @Test fun completeAndFailed() {
        val done = ApiJson.status("""{"id":"x","state":"complete","stage":"ARRANGE","completed":1,"total":1,"eta_sec":0}""")
        assertTrue(done.toProgress().done)
        assertEquals(1f, done.toProgress().overall, 1e-6f)
        val failed = ApiJson.status("""{"id":"x","state":"failed","stage":"TRANSCRIBE","error":"RuntimeError: boom"}""")
        assertTrue(failed.isFailed)
        assertEquals("RuntimeError: boom", failed.error)
    }

    @Test fun unknownStageFallsBackToSeparate() {
        assertEquals(Stage.SEPARATE, ApiJson.status("""{"id":"x","state":"running","stage":"NEW"}""").stage)
    }

    @Test fun resultListsFilesPerPart() {
        val r = ApiJson.result(
            """{"id":"x","title":"Immigrant Song",
               "full_band":{"pdf":"scores/full_band.pdf","pages":5,"midi":"full_score.mid"},
               "instruments":{"guitar":{"pdf":"scores/guitar.pdf","pages":2,"midi":"guitar/guitar.mid"},
                              "piano":{"pdf":"scores/piano.pdf","pages":2}},
               "original_parts":["guitar"],"generated_parts":["piano"]}"""
        )
        assertEquals("full_score.mid", r.fullBand.midi)
        assertEquals(setOf("guitar", "piano"), r.instruments.keys)
        assertNull(r.instruments["piano"]!!.midi)
        assertEquals(listOf("piano"), r.generatedParts)
    }
}
