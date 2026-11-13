// AI-generated with Claude Code, 2026-11-13
package com.team3.rocky.progress

import com.team3.rocky.server.ApiException
import com.team3.rocky.server.JobFailedException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

/**
 * 실패를 '이 곡 그대로 다시 시도'와 '목록에서 빼고 새로 만들기'로 나누는 규칙
 * (조수빈 'ROCKY 곡 처리 결과별 동작', 서버 #25, PR #24 코멘트).
 */
class FailureTest {
    private fun server(code: String?, retryable: Boolean?, wait: Int? = null, from: String? = "gpu", message: String? = "서버 안내") =
        JobFailedException("dev text", null, code, message, retryable, wait, from)

    @Test fun pdfNetworkWaitsSixtySecondsAndRedoesOnlyThePdf() {
        val f = ScoreJobs.classify(server("pdf_network", true, wait = 60, from = "pdf"))
        assertTrue(f.retry)
        assertEquals(60, f.waitSec)
        assertTrue(f.message.contains("1분 뒤에 다시 시도하면"))
        assertTrue(f.message.contains("PDF만 다시"))
    }

    @Test fun timeoutCanBeRetriedRightAway() {
        val f = ScoreJobs.classify(server("timeout", true, from = "gpu"))
        assertTrue(f.retry)
        assertNull(f.waitSec)
        assertTrue(f.message.contains("멈춘 곳부터"))
    }

    @Test fun pipelineErrorAsksToTellTheTeamAfterTwoFailures() {
        val f = ScoreJobs.classify(server("pipeline_error", true, from = "pdf"))
        assertTrue(f.retry)
        assertTrue(f.message.contains("PDF만 다시"))
        assertTrue(f.message.contains("두 번 연속"))
    }

    @Test fun noAgentAndInterruptedUploadStartOver() {
        val noAgent = ScoreJobs.classify(server("no_agent", false))
        assertFalse(noAgent.retry)
        assertTrue(noAgent.message.contains("팀에게 알려"))
        val upload = ScoreJobs.classify(server("upload_interrupted", false, from = null))
        assertFalse(upload.retry)
        assertTrue(upload.message.contains("다시 올려"))
    }

    @Test fun refusedInputIsNeverRetried() {
        val f = ScoreJobs.classify(JobFailedException("밴드 곡을 올려 주세요.", reason = "too_short"))
        assertFalse(f.retry)
        assertEquals("곡이 너무 짧아서 악보를 만들 수 없어요. 30초 넘는 곡을 올려 주세요.", f.message)
    }

    @Test fun oldServerFailureStartsOver() {
        // #25 전 서버는 retryable을 보내지 않는다: 같은 곡을 다시 돌릴 방법이 없으니 새로 만든다.
        val f = ScoreJobs.classify(JobFailedException("beat_this exited 1"))
        assertFalse(f.retry)
    }

    @Test fun unknownNewCodeShowsTheServersKoreanText() {
        val f = ScoreJobs.classify(server("disk_full", false, message = "볼륨이 가득 찼어요."))
        assertEquals("볼륨이 가득 찼어요.", f.message)
    }

    @Test fun uploadTimeRefusalsStartOver() {
        listOf(404, 410, 413, 415, 422).forEach { code ->
            assertFalse("HTTP $code", ScoreJobs.classify(ApiException(code, "HTTP $code")).retry)
        }
        assertTrue(ScoreJobs.classify(ApiException(410, "gone")).message.contains("다시 올려"))
    }

    @Test fun connectionProblemsCanBeRetried() {
        assertTrue(ScoreJobs.classify(IOException("timeout")).retry)
        assertTrue(ScoreJobs.classify(ApiException(503, "busy")).retry)
        assertTrue(ScoreJobs.classify(ApiException(401, "key")).retry)
    }

    @Test fun missingFileStartsOver() {
        assertFalse(ScoreJobs.classify(FileGoneException()).retry)
    }

    @Test fun serverNotesBecomeShortUserText() {
        assertEquals("PDF를 다시 만드는 중 (2/3)", ScoreJobs.noteText("악보 PDF 만들기를 다시 시도하는 중 (2/3)"))
        assertEquals("앞의 곡이 끝나길 기다리는 중", ScoreJobs.noteText("GPU를 다른 작업이 쓰고 있어서 기다리는 중"))
        assertEquals("곧 시작해요 · 준비하는 중", ScoreJobs.noteText("노트북 연결(agent)을 기다리는 중"))
        assertNull(ScoreJobs.noteText("unified.py stage 3"))
        assertNull(ScoreJobs.noteText(null))
    }
}
