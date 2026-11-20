// AI-generated with Claude Code, 2026-11-20
package com.team3.rocky.auth

import com.team3.rocky.server.MemberApi
import com.team3.rocky.server.MemberApiException
import com.team3.rocky.testutil.FakeHttp
import com.team3.rocky.testutil.FakeHttp.Companion.json
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** 서버 회원 DB를 쓰는 [ServerAccounts]: 응답 해석, 중복·잘못된 로그인 처리 */
class ServerAccountsTest {
    private val userJson = """{"id":4,"email":"a@b.com","nickname":"가나","instruments":["bass"],"provider":"EMAIL","created_at":100}"""

    private fun accounts(s: FakeHttp) = ServerAccounts { token -> MemberApi(s.url, "", token) }

    @Test fun signUpAndLoginReturnSessionWithToken() {
        FakeHttp(mapOf(
            "POST /auth/signup" to json(201, """{"token":"t1","user":$userJson}"""),
            "POST /auth/login" to json(200, """{"token":"t2","user":$userJson}"""),
        )).use { s ->
            val a = accounts(s)
            val up = a.signUp("a@b.com", "12345678a", "가나", listOf("bass"), 0)
            assertEquals("t1", up.token)
            assertEquals(User(4, "a@b.com", "가나", listOf("bass"), AuthProvider.EMAIL, 100), up.user)
            val body = JSONObject(String(s.requests[0].body, Charsets.UTF_8))
            assertEquals("bass", body.getJSONArray("instruments").getString(0))
            assertEquals("t2", a.login("a@b.com", "12345678a", 0)!!.token)
        }
    }

    @Test fun duplicateEmailOrNicknameBecomesDuplicateException() {
        FakeHttp(mapOf(
            "POST /auth/signup" to json(409, """{"detail":"이미 가입된 이메일이에요","field":"email"}"""),
            "PATCH /me" to json(409, """{"detail":"이미 사용 중인 닉네임이에요","field":"nickname"}"""),
        )).use { s ->
            val a = accounts(s)
            try {
                a.signUp("a@b.com", "12345678a", "가나", emptyList(), 0); fail()
            } catch (e: UserDatabase.DuplicateException) {
                assertEquals("email", e.column)
            }
            try {
                a.updateProfile(Session(User(4, "a@b.com", "가나", emptyList(), AuthProvider.EMAIL, 0), "t"), "다라", emptyList()); fail()
            } catch (e: UserDatabase.DuplicateException) {
                assertEquals(UserDatabase.C_NICKNAME, e.column)
            }
        }
    }

    @Test fun otherServerErrorsAreNotHidden() {
        FakeHttp(mapOf(
            "POST /auth/signup" to json(409, """{"detail":"conflict"}"""),
            "POST /auth/login" to json(500, """{"detail":"down"}"""),
        )).use { s ->
            val a = accounts(s)
            try { a.signUp("a@b.com", "p", "n", emptyList(), 0); fail() } catch (e: MemberApiException) { assertEquals(409, e.code) }
            try { a.login("a@b.com", "p", 0); fail() } catch (e: MemberApiException) { assertEquals(500, e.code) }
        }
    }

    @Test fun wrongPasswordGivesNull() {
        FakeHttp(mapOf("POST /auth/login" to json(401, """{"detail":"wrong email or password"}"""))).use { s ->
            assertNull(accounts(s).login("a@b.com", "x", 0))
        }
    }

    @Test fun takenChecksAndProfileUpdate() {
        FakeHttp(mapOf(
            "GET /auth/taken?email=a%40b.com" to json(200, """{"taken":true}"""),
            "GET /auth/taken?nickname=%EB%8B%A4%EB%9D%BC" to json(200, """{"taken":false}"""),
            "PATCH /me" to json(200, userJson.replace("가나", "다라")),
        )).use { s ->
            val a = accounts(s)
            val me = Session(User(4, "a@b.com", "가나", emptyList(), AuthProvider.EMAIL, 0), "tok")
            assertTrue(a.emailTaken("a@b.com"))
            assertFalse(a.nicknameTaken("다라", me))
            assertEquals("Bearer tok", s.requests[1].headers["authorization"])
            assertEquals("다라", a.updateProfile(me, "다라", listOf("bass")).nickname)
        }
    }

    @Test fun logoutIgnoresAnUnreachableServer() {
        val a = ServerAccounts { token -> MemberApi("http://127.0.0.1:9", "", token) }
        a.logout(Session(User(1, "a@b.com", "n", emptyList(), AuthProvider.EMAIL, 0), "t"))   // 예외 없이 끝남
    }

    @Test fun userJsonRoundTripAndUnknownProvider() {
        val u = User(7, "c@d.com", "닉", listOf("piano", "drums"), AuthProvider.GOOGLE, 42)
        assertEquals(u, ServerAccounts.user(ServerAccounts.toJson(u)))
        val odd = JSONObject(userJson).put("provider", "KAKAO")
        assertEquals(AuthProvider.EMAIL, ServerAccounts.user(odd).provider)
    }
}
