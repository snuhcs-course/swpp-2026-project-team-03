// AI-generated with Claude Code, 2026-11-01
package com.team3.rocky.server

import com.sun.net.httpserver.HttpServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.net.InetSocketAddress

/** JDK에 들어 있는 작은 HTTP 서버로 실제 요청 모양(헤더, multipart, 오류 코드)을 확인한다. */
class RockyApiTest {
    @get:Rule val tmp = TemporaryFolder()
    private lateinit var http: HttpServer
    private var lastBody = ""
    private var lastKey: String? = null
    private var lastType: String? = null
    private var lastMethod: String? = null

    @Before fun start() {
        http = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        http.createContext("/") { ex ->
            lastKey = ex.requestHeaders.getFirst("X-Rocky-Key")
            lastType = ex.requestHeaders.getFirst("Content-Type")
            lastMethod = ex.requestMethod
            lastBody = ex.requestBody.readBytes().toString(Charsets.UTF_8)
            val (code, body) = when (ex.requestURI.path) {
                "/jobs" -> 201 to """{"id":"abc123abc123","state":"queued"}"""
                "/jobs/abc123abc123" -> 200 to """{"id":"abc123abc123","state":"running","stage":"BEATS","completed":0,"total":1}"""
                "/jobs/abc123abc123/files/scores/full_band.pdf" -> 200 to "%PDF-1.4 fake"
                "/jobs/abc123abc123/transpositions/-1" -> 200 to """{"id":"abc123abc123","title":"Song","full_band":{"pdf":"scores/full_band.pdf"},"instruments":{}}"""
                "/jobs/abc123abc123/transpositions/-1/files/scores/full_band.pdf" -> 200 to "%PDF-1.4 shifted"
                else -> 404 to """{"detail":"no such job"}"""
            }
            val bytes = body.toByteArray()
            ex.sendResponseHeaders(code, bytes.size.toLong())
            ex.responseBody.use { it.write(bytes) }
        }
        http.start()
    }

    @After fun stop() = http.stop(0)

    private fun api(key: String = "secret") = RockyApi("http://127.0.0.1:${http.address.port}/", key)

    @Test fun uploadSendsMultipartWithKey() {
        val id = api().upload(
            "RIFFdata".byteInputStream(), "밤을 달리다.mp3", "밤을 달리다", listOf("piano", "guitar"),
            original = listOf("guitar"), lineup = listOf("piano", "guitar", "guitar2"),
        )
        assertEquals("abc123abc123", id)
        assertEquals("secret", lastKey)
        assertTrue(lastType!!.startsWith("multipart/form-data; boundary="))
        assertTrue(lastBody.contains("name=\"requested\"\r\n\r\npiano,guitar\r\n"))
        assertTrue(lastBody.contains("name=\"title\"\r\n\r\n밤을 달리다\r\n"))
        assertTrue(lastBody.contains("name=\"original\"\r\n\r\nguitar\r\n"))
        assertTrue(lastBody.contains("name=\"lineup\"\r\n\r\npiano,guitar,guitar2\r\n"))
        assertTrue(lastBody.contains("filename=\" .mp3\""))
        assertTrue(lastBody.contains("RIFFdata"))
    }

    @Test fun statusIsParsed() {
        assertEquals("BEATS", api().status("abc123abc123").stage.name)
    }

    @Test fun noKeyHeaderWhenKeyIsBlank() {
        api(key = "").status("abc123abc123")
        assertEquals(null, lastKey)
    }

    @Test fun errorCodeBecomesApiException() {
        try {
            api().status("000000000000")
            fail("expected ApiException")
        } catch (e: ApiException) {
            assertEquals(404, e.code)
        }
    }

    @Test fun downloadWritesFile() {
        val dest = tmp.root.resolve("scores/full_band.pdf")
        api().download("abc123abc123", "scores/full_band.pdf", dest)
        assertEquals("%PDF-1.4 fake", dest.readText())
    }

    @Test fun transposeAndDownloadShiftedScore() {
        val result = api().transpose("abc123abc123", -1)
        assertEquals("POST", lastMethod)
        assertEquals("scores/full_band.pdf", result.fullBand.pdf)
        val dest = tmp.root.resolve("transposed/full_band.pdf")
        api().downloadTransposed("abc123abc123", -1, result.fullBand.pdf, dest)
        assertEquals("%PDF-1.4 shifted", dest.readText())
    }

    @Test fun healthIsFalseWhenNothingListens() {
        assertEquals(false, RockyApi("http://127.0.0.1:1", "").health())
    }
}
