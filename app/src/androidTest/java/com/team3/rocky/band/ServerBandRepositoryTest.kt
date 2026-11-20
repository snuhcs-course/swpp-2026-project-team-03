// AI-generated with Claude Code, 2026-11-20
package com.team3.rocky.band

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.team3.rocky.Work
import com.team3.rocky.auth.ServerAccounts
import com.team3.rocky.auth.Session
import com.team3.rocky.server.MemberApi
import com.team3.rocky.server.RockyApi
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * 서버 밴드 DB를 쓰는 [ServerBandRepository]와 회원 API를, 실제 서버 코드(CI의 android-e2e가 10.0.2.2:8000에 띄움)에
 * 두 계정으로 붙여 본다. 서버가 없으면 건너뛴다.
 */
@RunWith(AndroidJUnit4::class)
class ServerBandRepositoryTest {
    private val ctx: Context = ApplicationProvider.getApplicationContext()
    private val url = InstrumentationRegistry.getArguments().getString("rockyServer") ?: "http://10.0.2.2:8000"
    private val accounts = ServerAccounts { token -> MemberApi(url, "", token) }
    private lateinit var a: Session
    private lateinit var b: Session

    private fun repo(s: Session) = ServerBandRepository(ctx) { MemberApi(url, "", s.token) }

    @Before fun twoMembers() {
        assumeTrue("ROCKY 서버($url)가 없어서 건너뜀", RockyApi(url, "").health())
        val tag = System.nanoTime().toString().takeLast(9)
        a = accounts.signUp("a$tag@test.com", "12345678a", "a$tag", emptyList(), 0)
        b = accounts.signUp("b$tag@test.com", "12345678a", "b$tag", emptyList(), 0)
    }

    @Test fun createJoinShareAndLeave() = runBlocking {
        val created = repo(a).create(a.user, "  테스트 밴드 ", "guitar,piano")
        assertTrue(created.toString(), created is BandResult.Success)
        val band = (created as BandResult.Success).band
        assertEquals("테스트 밴드", band.name)
        assertEquals(a.user.id, band.ownerId)

        val joined = repo(b).join(b.user, band.inviteCode.lowercase().chunked(3).joinToString("-"), "bass,drums")
        assertTrue(joined.toString(), joined is BandResult.Success)

        val mine = repo(b).myBands(b.user).single()
        assertEquals(2, mine.memberCount)
        assertEquals(0, mine.scoreCount)

        // 공유: 서버 작업 번호가 없는 악보도 올라가고, 다른 멤버가 같은 곡을 본다
        val work = Work(id = 501, title = "공유 곡", instruments = listOf("bass", "drums"), date = "2026.11.20 18:00")
        assertTrue(repo(a).share(a.user, band.id, work))
        assertTrue(repo(a).isShared(a.user.id, 501))
        val detail = repo(b).detail(band.id)!!
        assertEquals(setOf("bass", "drums"), detail.partsOf(b.user.id).toSet())
        assertTrue(detail.members.single { it.userId == a.user.id }.isOwner)
        val shared = detail.scores.single()
        assertEquals("공유 곡", shared.work.title)
        assertEquals(a.user.id, shared.sharedById)
        assertNull(shared.jobId)

        assertTrue(repo(a).renameScore(a.user, band.id, shared.id, "새 이름"))
        assertFalse(repo(a).renameScore(a.user, band.id, shared.id, "   "))
        assertEquals("새 이름", repo(b).detail(band.id)!!.scores.single().work.title)
        repo(a).renameMyWork(a.user.id, 501, "내 곡 이름")
        repo(a).updateNickname(a.user)

        val renamed = repo(a).rename(a.user, band.id, "새 밴드")
        assertEquals("새 밴드", (renamed as BandResult.Success).band.name)
        assertTrue(repo(a).rename(a.user, band.id, "") is BandResult.Failure)

        repo(b).leave(b.user, band.id)
        assertTrue(repo(b).myBands(b.user).isEmpty())
    }

    @Test fun wrongCodesAndNamesAreRejected() = runBlocking {
        assertTrue(repo(a).create(a.user, "", "guitar") is BandResult.Failure)
        assertTrue(repo(b).join(b.user, "12", "bass") is BandResult.Failure)          // 형식이 틀림 (서버까지 안 감)
        val missing = repo(b).join(b.user, "ZZZZZZ", "bass")                            // 없는 코드 (서버가 거절)
        assertTrue(missing is BandResult.Failure)
        assertTrue((missing as BandResult.Failure).message.isNotBlank())
        assertNull(repo(b).detail(999_999))
    }

    @Test fun unreachableServerGivesEmptyResultsAndAMessage() = runBlocking {
        val off = ServerBandRepository(ctx) { MemberApi("http://10.0.2.2:9", "", a.token) }
        assertTrue(off.myBands(a.user).isEmpty())
        assertNull(off.detail(1))
        assertFalse(off.isShared(a.user.id, 1))
        val r = off.create(a.user, "밴드", "guitar")
        assertTrue(r is BandResult.Failure)
    }

    @Test fun accountApiAgainstTheServer() {
        assertTrue(accounts.emailTaken(a.user.email))
        assertFalse(accounts.nicknameTaken("nobody-${System.nanoTime()}", a))
        assertEquals(a.user.id, accounts.login(a.user.email, "12345678a", 0)!!.user.id)
        assertNull(accounts.login(a.user.email, "wrong-password1", 0))
        val updated = accounts.updateProfile(a, a.user.nickname + "x", listOf("drums"))
        assertEquals(listOf("drums"), updated.instruments)

        // 프로필 사진: 올리고, 다른 멤버가 받고, 지우면 없음
        val png = byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A) + ByteArray(64) { it.toByte() }
        val api = MemberApi(url, "", a.token)
        api.bytes("PUT", "/me/photo", png, "image/png")
        assertArrayEquals(png, MemberApi(url, "", b.token).bytes("GET", "/users/${a.user.id}/photo"))
        api.call("DELETE", "/me/photo")
        assertNull(MemberApi(url, "", b.token).bytes("GET", "/users/${a.user.id}/photo"))
        accounts.logout(a)
    }
}
