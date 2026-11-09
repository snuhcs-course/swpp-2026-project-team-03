// AI-generated with Claude Code, 2026-10-15
package com.team3.rocky.auth

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AuthRepositoryTest {
    private val ctx = ApplicationProvider.getApplicationContext<Context>()
    private lateinit var db: UserDatabase
    private lateinit var auth: AuthRepository

    private val form = SignUpForm(
        email = "Rocky@SNU.ac.kr", password = "band2026", passwordConfirm = "band2026",
        nickname = "락스타", instruments = setOf("guitar", "drums"),
        over14 = true, agreeTerms = true, agreePrivacy = true,
    )

    @Before fun setUp() {
        db = UserDatabase(ctx, name = null)   // in-memory: the app's real DB is not touched
        auth = AuthRepository(ctx, LocalAccounts(db))
        auth.logout()
    }

    @After fun tearDown() { auth.logout(); db.close() }

    @Test fun signUpStoresUserAndLogsIn() = runBlocking {
        val r = auth.signUp(form) as AuthResult.Success
        assertEquals("rocky@snu.ac.kr", r.user.email)
        assertEquals("락스타", r.user.nickname)
        assertEquals(listOf("drums", "guitar"), r.user.instruments)   // kept in app order
        assertEquals(AuthProvider.EMAIL, r.user.provider)
        assertEquals(r.user, auth.currentUser())
    }

    @Test fun passwordIsStoredHashed() = runBlocking {
        auth.signUp(form)
        val stored = db.findCredentials("rocky@snu.ac.kr")!!.second!!
        assertTrue(stored.startsWith("pbkdf2-sha256$"))
        assertTrue("band2026" !in stored)
    }

    @Test fun duplicateEmailAndNicknameAreRejected() = runBlocking {
        auth.signUp(form)
        val again = auth.signUp(form.copy(email = "rocky@snu.ac.kr ", nickname = "다른이름")) as AuthResult.Invalid
        assertEquals(setOf(SignUpValidator.Field.EMAIL), again.errors.keys)
        val sameNick = auth.signUp(form.copy(email = "other@snu.ac.kr")) as AuthResult.Invalid
        assertEquals(setOf(SignUpValidator.Field.NICKNAME), sameNick.errors.keys)
    }

    @Test fun loginLogoutCycle() = runBlocking {
        auth.signUp(form)
        auth.logout()
        assertNull(auth.currentUser())

        val wrong = auth.login("rocky@snu.ac.kr", "band2027") as AuthResult.Failure
        assertEquals(AuthRepository.WRONG_CREDENTIALS, wrong.message)
        val unknown = auth.login("nobody@snu.ac.kr", "band2026") as AuthResult.Failure
        assertEquals(wrong.message, unknown.message)   // same message: no hint which part was wrong
        assertNull(auth.currentUser())

        val ok = auth.login("  ROCKY@snu.ac.kr", "band2026") as AuthResult.Success
        assertEquals("락스타", ok.user.nickname)
        assertNotNull(auth.currentUser())
    }
}
