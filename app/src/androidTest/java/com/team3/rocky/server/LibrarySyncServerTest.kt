// AI-generated with Claude Code, 2026-11-26
package com.team3.rocky.server

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.team3.rocky.Work
import com.team3.rocky.WorkStore
import com.team3.rocky.auth.LoggedInElsewhereException
import com.team3.rocky.auth.ServerAccounts
import com.team3.rocky.auth.Session
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * 보관함이 계정을 따라간다 + 한 계정은 한 폰에서만 (실제 서버 코드, CI android-e2e).
 * 폰 두 대는 기기 번호를 다르게 보내고, 폰을 바꾸는 것은 이 폰의 저장 내용을 지워서 흉내 낸다.
 */
@RunWith(AndroidJUnit4::class)
class LibrarySyncServerTest {
    private val ctx: Context = ApplicationProvider.getApplicationContext()
    private val url = InstrumentationRegistry.getArguments().getString("rockyServer") ?: "http://10.0.2.2:8000"
    private val phoneA = ServerAccounts({ "test-phone-A" }) { t -> MemberApi(url, "", t) }
    private val phoneB = ServerAccounts({ "test-phone-B" }) { t -> MemberApi(url, "", t) }
    private val factory = LibrarySync.apiFactory

    @Before fun serverIsUp() {
        assumeTrue("ROCKY 서버($url)가 없어서 건너뜀", RockyApi(url, "").health())
        ServerSettings.save(ctx, url, "")
        LibrarySync.apiFactory = { c -> com.team3.rocky.auth.AuthRepository.token(c)?.let { MemberApi(url, "", it) } }
        newPhone()
    }

    @After fun restore() {
        LibrarySync.apiFactory = factory
        newPhone()
    }

    /** 다른 폰처럼: 로그인·보관함·동기화 기록이 없는 상태. */
    private fun newPhone() {
        for (name in listOf("rocky_session", "rocky", "rocky_library_sync")) {
            ctx.getSharedPreferences(name, Context.MODE_PRIVATE).edit().clear().commit()
        }
    }

    /** AuthRepository가 로그인할 때 저장하는 것과 같은 세션. */
    private fun useSession(s: Session) {
        ctx.getSharedPreferences("rocky_session", Context.MODE_PRIVATE).edit()
            .putLong("user_id", s.user.id).putString("token", s.token)
            .putString("user", ServerAccounts.toJson(s.user).toString()).commit()
    }

    private fun aJob(): String =
        RockyApi(url, "").upload(ByteArray(4096) { (it % 251).toByte() }.inputStream(), "sync.wav", "동기화 곡", listOf("piano"))

    @Test fun libraryFollowsTheAccountAndOnlyOnePhoneIsLoggedIn() = runBlocking {
        val tag = System.nanoTime() % 1_000_000_000
        val email = "sync$tag@test.com"
        val a = phoneA.signUp(email, "12345678a", "s$tag", emptyList(), 0)
        useSession(a)

        // 폰 A에서 악보가 완성되어 보관함에 저장된다
        val job = aJob()
        val work = Work(1_764_000_000_000 + tag, "동기화 곡", listOf("piano"), "2026.11.26 17:00", jobId = job)
        WorkStore.add(ctx, work)
        LibrarySync.sync(ctx)
        val onServer = JSONArray(MemberApi(url, "", a.token).get("/me/works"))
        assertEquals(1, onServer.length())
        assertEquals(job, onServer.getJSONObject(0).getString("job_id"))

        // 폰 A가 로그인해 있으면 폰 B는 먼저 경고를 받는다
        try {
            phoneB.login(email, "12345678a", 0)
            throw AssertionError("경고 없이 두 번째 폰이 로그인됐어요")
        } catch (e: LoggedInElsewhereException) { }

        // 경고를 확인하면(force) 폰 B로 넘어오고, 폰 A는 다음 요청에서 로그아웃된다
        newPhone()
        val b = phoneB.login(email, "12345678a", 0, force = true)!!
        var kicked = false
        MemberApi.onLoginRequired = { kicked = true }
        try {
            MemberApi(url, "", a.token).get("/me"); throw AssertionError("폰 A가 아직 로그인되어 있어요")
        } catch (e: MemberApiException) {
            assertEquals(401, e.code)
        } finally {
            MemberApi.onLoginRequired = null
        }
        assertTrue("어느 회원 API든 로그아웃을 알려야 해요", kicked)
        useSession(b)
        assertTrue(WorkStore.load(ctx).isEmpty())
        assertTrue(LibrarySync.sync(ctx))
        val there = WorkStore.load(ctx)
        assertEquals(listOf(work.id), there.map { it.id })
        assertEquals(job, there[0].jobId)
        assertEquals("동기화 곡", there[0].title)

        // 폰 B에서 지우면 서버 보관함에서도 빠진다
        WorkStore.remove(ctx, work.id)
        LibrarySync.sync(ctx)
        assertEquals(0, JSONArray(MemberApi(url, "", b.token).get("/me/works")).length())
        phoneB.logout(b)
    }

    /** 순형 리뷰: 서버가 받지 않는 곡(다른 서버 주소에서 만든 곡 등)은 보관함과 폰에서 지우지 않는다. */
    @Test fun songTheServerDoesNotKnowStaysOnThisPhone() = runBlocking {
        val tag = System.nanoTime() % 1_000_000_000
        val a = phoneA.signUp("local$tag@test.com", "12345678a", "l$tag", emptyList(), 0)
        useSession(a)
        val work = Work(1_765_000_000_000 + tag, "다른 서버 곡", listOf("drums"), "2026.11.27", jobId = "0123456789ab")
        val files = ScoreStore.dir(ctx, work.id).apply { mkdirs(); resolve("full.pdf").writeText("pdf") }
        WorkStore.add(ctx, work)
        repeat(2) { LibrarySync.sync(ctx) }   // 두 번째 동기화에서도 지우지 않는다
        assertEquals(listOf(work.id), WorkStore.load(ctx).map { it.id })
        assertTrue(files.resolve("full.pdf").exists())
        assertEquals(0, JSONArray(MemberApi(url, "", a.token).get("/me/works")).length())
        WorkStore.remove(ctx, work.id)
        files.deleteRecursively()
        phoneA.logout(a)
    }
}
