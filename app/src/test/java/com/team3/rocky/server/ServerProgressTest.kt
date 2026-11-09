// AI-generated with Claude Code, 2026-11-01
package com.team3.rocky.server

import com.team3.rocky.progress.Stage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.io.IOException
import java.io.InputStream

class ServerProgressTest {
    private fun status(state: String, stage: Stage = Stage.TRANSCRIBE, done: Int = 0, error: String? = null) =
        JobStatus("job", state, stage, done, 10, null, null, error)

    /** 정해진 순서대로 응답(또는 예외)을 돌려주는 가짜 서버 */
    private class Scripted(vararg replies: Any) : ScoreServer {
        val left = ArrayDeque(replies.toList())
        var calls = 0
        override fun status(jobId: String): JobStatus {
            calls++
            return when (val r = left.removeFirst()) {
                is JobStatus -> r
                is Exception -> throw r
                else -> error("bad script")
            }
        }
        override fun upload(
            input: InputStream, fileName: String, title: String, requested: List<String>,
            original: List<String>, lineup: List<String>,
        ) = "job"
        override fun cancel(jobId: String) = "cancelled"
        override fun result(jobId: String) = throw UnsupportedOperationException()
        override fun download(jobId: String, path: String, dest: File) = throw UnsupportedOperationException()
    }

    private fun track(server: ScoreServer, maxMissed: Int = 3) =
        runBlocking { ServerProgress(server, pollMs = 0, maxMissed = maxMissed, io = Dispatchers.Unconfined).track("job").toList() }

    @Test fun emitsUntilComplete() {
        val server = Scripted(status("running", done = 3), status("running", done = 7), status("complete", Stage.ARRANGE))
        val out = track(server)
        assertEquals(listOf(3, 7), out.dropLast(1).map { it.completed })
        assertTrue(out.last().done)
        assertEquals(3, server.calls)
    }

    @Test fun shortNetworkDropsAreRetried() {
        val out = track(Scripted(IOException("drop"), IOException("drop"), status("complete", Stage.ARRANGE)))
        assertEquals(1, out.size)
        assertTrue(out.single().done)
    }

    @Test fun longNetworkLossFails() {
        try {
            track(Scripted(IOException("1"), IOException("2"), IOException("3")), maxMissed = 2)
            fail("expected IOException")
        } catch (e: IOException) {
            assertEquals("3", e.message)
        }
    }

    @Test fun serverFailureCarriesReason() {
        try {
            track(Scripted(status("running"), status("failed", error = "beat_this exited 1")))
            fail("expected JobFailedException")
        } catch (e: JobFailedException) {
            assertEquals("beat_this exited 1", e.message)
        }
    }

    @Test fun rejectedRequestIsNotRetried() {
        val server = Scripted(ApiException(401, "HTTP 401"), status("complete"))
        try {
            track(server)
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertEquals(401, e.code)
            assertEquals(1, server.calls)
        }
    }
}
