// AI-generated with Claude Code, 2026-11-21
package com.team3.rocky.server

import com.sun.net.httpserver.HttpServer
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.IOException
import java.net.InetSocketAddress

/**
 * 수업 공개 입구의 "돌려보내기"를 흉내 낸 서버로 FrontGate 재전송을 확인한다.
 * 연결이 통과되기 전에는 본문이 있는 요청에 307, GET에는 302(/<숫자>/<경로> → 원래 경로)를 보낸다.
 * GET /health 또는 /<숫자>/<경로>를 받으면 통과된 것으로 본다 (진짜 입구는 연결마다 따지지만 여기서는 한 번이면 통과).
 */
class FrontGateTest {
    private lateinit var http: HttpServer
    private var passed = false
    private var neverPass = false
    private var bounceUpload = false
    private val log = mutableListOf<String>()
    private val bodies = mutableListOf<String>()

    @Before fun start() {
        http = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        http.createContext("/") { ex ->
            val path = ex.requestURI.path
            val body = ex.requestBody.readBytes().toString(Charsets.UTF_8)
            log += "${ex.requestMethod} $path"
            if (body.isNotEmpty()) bodies += body
            fun reply(code: Int, text: String = "", location: String? = null) {
                location?.let { ex.responseHeaders.add("Location", it) }
                val bytes = text.toByteArray()
                ex.sendResponseHeaders(code, if (bytes.isEmpty()) -1 else bytes.size.toLong())
                if (bytes.isNotEmpty()) ex.responseBody.use { it.write(bytes) } else ex.close()
            }
            when {
                path == "/health" -> { if (!neverPass) passed = true; reply(200, """{"ok":true}""") }
                path.startsWith("/123/") -> { if (!neverPass) passed = true; reply(302, location = path.removePrefix("/123")) }
                path == "/jobs" && bounceUpload -> reply(307, location = "/123/jobs")
                !passed && ex.requestMethod == "GET" -> reply(302, location = "/123$path")
                !passed -> reply(307, location = "/123$path")
                path == "/auth/login" -> reply(200, """{"token":"t1"}""")
                path == "/me" -> reply(200, """{"id":7}""")
                path == "/jobs" -> reply(201, """{"id":"abc123abc123","state":"queued"}""")
                path == "/jobs/abc123abc123/cancel" -> reply(200, """{"id":"abc123abc123","state":"cancelled"}""")
                path == "/jobs/abc123abc123/rating" -> reply(200, "{}")
                else -> reply(404, """{"detail":"no"}""")
            }
        }
        http.start()
    }

    @After fun stop() = http.stop(0)

    private val url get() = "http://127.0.0.1:${http.address.port}"

    @Test fun bouncedLoginIsSentAgainAfterHealthCheck() {
        val text = MemberApi(url, "k", null).post("/auth/login", JSONObject().put("email", "a@b.c"))
        assertEquals("t1", JSONObject(text).getString("token"))
        assertEquals(listOf("POST /auth/login", "GET /health", "POST /auth/login"), log)
        // 같은 본문을 다시 보냈다
        assertEquals(2, bodies.size)
        assertEquals(bodies[0], bodies[1])
    }

    @Test fun getFollowsTheEntranceRedirectByItself() {
        val text = MemberApi(url, "k", "t").get("/me")
        assertEquals(7, JSONObject(text).getInt("id"))
        assertEquals(listOf("GET /me", "GET /123/me", "GET /me"), log)
    }

    @Test fun givesUpAfterThreeTriesWithTheHttpCode() {
        neverPass = true
        try {
            MemberApi(url, "k", null).post("/auth/login", JSONObject())
            fail("계속 돌려보내면 오류여야 함")
        } catch (e: MemberApiException) {
            assertEquals(307, e.code)
        }
        assertEquals(FrontGate.ATTEMPTS, log.count { it == "POST /auth/login" })
    }

    @Test fun cancelAndRatingAreSentAgain() {
        val api = RockyApi(url, "k")
        assertEquals("cancelled", api.cancel("abc123abc123"))
        assertEquals(listOf("POST /jobs/abc123abc123/cancel", "GET /health", "POST /jobs/abc123abc123/cancel"), log)
        log.clear(); bodies.clear(); passed = false
        api.rate("abc123abc123", 4, "Song", listOf("drums"))
        assertEquals(listOf("PUT /jobs/abc123abc123/rating", "GET /health", "PUT /jobs/abc123abc123/rating"), log)
        assertEquals(bodies[0], bodies[1])
    }

    @Test fun uploadChecksTheConnectionFirst() {
        val id = RockyApi(url, "k").upload(ByteArrayInputStream(ByteArray(64)), "song.mp3", "Song", listOf("drums"))
        assertEquals("abc123abc123", id)
        assertEquals(listOf("GET /health", "POST /jobs"), log)
    }

    @Test fun bouncedUploadIsAConnectionProblem() {
        bounceUpload = true
        try {
            RockyApi(url, "k").upload(ByteArrayInputStream(ByteArray(64)), "song.mp3", "Song", listOf("drums"))
            fail("돌려보내진 업로드는 오류여야 함")
        } catch (e: ApiException) {
            fail("서버 거절(ApiException)이 아니라 연결 문제(IOException)여야 함")
        } catch (e: IOException) {
            assertTrue(e.message!!.contains("307"))
        }
    }
}
