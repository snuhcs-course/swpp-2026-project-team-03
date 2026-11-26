// AI-generated with Claude Code, 2026-11-20
package com.team3.rocky.server

import com.team3.rocky.testutil.FakeHttp
import com.team3.rocky.testutil.FakeHttp.Companion.json
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** 회원·밴드 서버 API 클라이언트: 헤더, 본문, 오류 해석, 사진(바이트) 요청 */
class MemberApiTest {
    @Test fun sendsKeyTokenAndJsonBody() {
        FakeHttp(mapOf("POST /bands" to json(201, """{"id":3}"""))).use { s ->
            val text = MemberApi(s.url + "/", "secret", "tok").post("/bands", JSONObject().put("name", "밴드"))
            assertEquals(3, JSONObject(text).getInt("id"))
            val r = s.requests.single()
            assertEquals("secret", r.headers["x-rocky-key"])
            assertEquals("Bearer tok", r.headers["authorization"])
            assertTrue(r.headers["content-type"]!!.startsWith("application/json"))
            assertEquals("밴드", JSONObject(String(r.body, Charsets.UTF_8)).getString("name"))
        }
    }

    @Test fun noKeyOrTokenMeansNoHeaders() {
        FakeHttp(mapOf("GET /bands" to json(200, "[]"))).use { s ->
            MemberApi(s.url, "", null).get("/bands")
            val r = s.requests.single()
            assertNull(r.headers["x-rocky-key"])
            assertNull(r.headers["authorization"])
        }
    }

    @Test fun serverRejectionCarriesDetailAndField() {
        FakeHttp(mapOf("POST /bands/join" to json(404, """{"detail":"이 초대 코드로 된 밴드가 없어요","field":"code"}"""))).use { s ->
            try {
                MemberApi(s.url, "", "t").post("/bands/join", JSONObject())
                fail("거절되어야 함")
            } catch (e: MemberApiException) {
                assertEquals(404, e.code)
                assertEquals("이 초대 코드로 된 밴드가 없어요", e.message)
                assertEquals("code", e.field)
            }
        }
    }

    @Test fun nonJsonErrorFallsBackToHttpCode() {
        FakeHttp(mapOf("GET /me" to (500 to "oops".toByteArray()))).use { s ->
            try {
                MemberApi(s.url, "", "t").get("/me")
                fail("거절되어야 함")
            } catch (e: MemberApiException) {
                assertEquals(500, e.code)
                assertEquals("HTTP 500", e.message)
                assertNull(e.field)
            }
        }
    }

    @Test fun photoBytesUploadDownloadAndMissing() {
        val png = byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 1, 2, 3)
        FakeHttp(mapOf(
            "PUT /me/photo" to json(200, """{"photo_at":5}"""),
            "GET /users/1/photo" to (200 to png),
            "GET /users/9/photo" to json(404, """{"detail":"no photo"}"""),
            "GET /users/2/photo" to json(500, "{}"),
        )).use { s ->
            val api = MemberApi(s.url, "k", "t")
            api.bytes("PUT", "/me/photo", png, "image/png")
            assertEquals("image/png", s.requests[0].headers["content-type"])
            assertArrayEquals(png, s.requests[0].body)
            assertArrayEquals(png, api.bytes("GET", "/users/1/photo"))
            assertNull(api.bytes("GET", "/users/9/photo"))
            try {
                api.bytes("GET", "/users/2/photo")
                fail("500은 예외")
            } catch (e: MemberApiException) {
                assertEquals(500, e.code)
            }
        }
    }

    @Test fun helpers() {
        assertEquals("a%40b.com", MemberApi.q("a@b.com"))
        assertEquals(listOf("bass", "piano"), MemberApi.strings(JSONArray(listOf("bass", "piano"))))
        assertEquals(emptyList<String>(), MemberApi.strings(null))
        val api = MemberApi("http://x", "", null)
        assertEquals(1, api.obj("""{"a":1}""").getInt("a"))
        assertEquals(2, api.arr("[1,2]").length())
    }

    // ---------- 다른 폰 로그인으로 세션이 끝났을 때 (순형 리뷰 3) ----------

    @Test fun anyMemberCallReportsLoginRequired() {
        var calls = 0
        MemberApi.onLoginRequired = { calls++ }
        try {
            FakeHttp(mapOf(
                "GET /bands" to json(401, """{"detail":"login required"}"""),
                "GET /me" to json(401, """{"detail":"missing or wrong X-Rocky-Key"}"""),
            )).use { s ->
                runCatching { MemberApi(s.url, "", "tok").get("/bands") }   // 밴드 API도 알린다
                runCatching { MemberApi(s.url, "", "tok").get("/me") }      // API 키가 틀린 401은 로그아웃이 아니다
                runCatching { MemberApi(s.url, "", null).get("/bands") }    // 로그인 전 요청도 아니다
            }
        } finally {
            MemberApi.onLoginRequired = null
        }
        assertEquals(1, calls)
    }
}
