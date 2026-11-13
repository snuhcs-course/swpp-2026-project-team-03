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
        assertNull(failed.reason)
        assertTrue(!failed.isRejected)
    }

    @Test fun rejectedInputCarriesReason() {
        val s = ApiJson.status("""{"id":"x","state":"failed","stage":"TRANSCRIBE","reason":"not_band_audio","error":"밴드 곡을 올려 주세요."}""")
        assertTrue(s.isRejected)
        assertEquals("not_band_audio", s.reason)
    }

    @Test fun unknownStageFallsBackToSeparate() {
        assertEquals(Stage.SEPARATE, ApiJson.status("""{"id":"x","state":"running","stage":"NEW"}""").stage)
    }

    @Test fun cancelledStatusAndCancelResponse() {
        val status = ApiJson.status("""{"id":"x","state":"cancelled","stage":"SEPARATE"}""")
        assertTrue(status.isCancelled)
        assertFalse(status.toProgress().done)
        assertEquals("cancelling", ApiJson.jobState("""{"id":"x","state":"cancelling"}"""))
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
        assertEquals(emptyList<String>(), r.faintParts)  // older servers send no faint_parts
    }

    @Test fun resultListsFaintParts() {
        val r = ApiJson.result(
            """{"id":"x","title":"t","full_band":{"pdf":"scores/full_band.pdf"},
               "instruments":{"piano":{"pdf":"scores/piano.pdf"}},
               "original_parts":["piano"],"generated_parts":[],"faint_parts":["piano"]}"""
        )
        assertEquals(listOf("piano"), r.faintParts)
    }

    @Test fun failedStatusCarriesRetryInfo() {
        val s = ApiJson.status(
            """{"id":"x","state":"failed","queue_position":null,"error":"PodFailed","reason":null,
               "error_code":"pdf_network","message":"인터넷이 끊겼어요","retryable":true,"retry_after_sec":60,
               "retry_from":"pdf","stage":"ARRANGE","completed":0,"total":1,"eta_sec":null}"""
        )
        assertEquals("pdf_network", s.errorCode)
        assertEquals(true, s.retryable)
        assertEquals(60, s.retryAfterSec)
        assertEquals("pdf", s.retryFrom)
        val e = JobFailedException.of(s)
        assertEquals("인터넷이 끊겼어요", e.userMessage)
        assertEquals(60, e.retryAfterSec)
    }

    @Test fun oldServerHasNoRetryInfo() {
        val s = ApiJson.status("""{"id":"x","state":"failed","error":"boom","stage":"SEPARATE","completed":0,"total":1}""")
        assertNull(s.errorCode)
        assertNull(s.retryable)
        assertNull(s.retryAfterSec)
    }

    @Test fun resultCarriesTheGuitarCountTheModelHeard() {
        val base = """"title":"t","full_band":{"pdf":"b.pdf"},"instruments":{},"original_parts":["guitar"],"generated_parts":[]"""
        assertEquals(2, ApiJson.result("""{"id":"x",$base,"original_guitars":2}""").originalGuitars)
        assertNull(ApiJson.result("""{"id":"x",$base,"original_guitars":null}""").originalGuitars)
        assertNull(ApiJson.result("""{"id":"x",$base}""").originalGuitars)
    }
}
