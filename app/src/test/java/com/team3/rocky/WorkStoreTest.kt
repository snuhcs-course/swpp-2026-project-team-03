package com.team3.rocky

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * U1, U2, U4, U8: 실제 SharedPreferences로 저장·불러오기 (Robolectric, 에뮬레이터 불필요)
 * 보관함은 로그인한 회원마다 따로 저장돼요 (AuthRepository의 세션 값을 직접 넣어서 흉내 냄).
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WorkStoreTest {

    private lateinit var ctx: Context

    /** AuthRepository가 로그인할 때 저장하는 값과 같은 위치에 회원 id를 넣어요. */
    private fun loginAs(userId: Long?) {
        val session = ctx.getSharedPreferences("rocky_session", Context.MODE_PRIVATE).edit()
        if (userId == null) session.remove("user_id") else session.putLong("user_id", userId)
        session.commit()
    }

    @Before
    fun setUp() {
        ctx = ApplicationProvider.getApplicationContext()
        WorkStore.clear(ctx)
        loginAs(1L)
    }

    @Test
    fun emptyStore_loadsEmptyList() {
        assertTrue(WorkStore.load(ctx).isEmpty())
    }

    @Test
    fun add_thenLoad_returnsSavedWork() {
        val w = Work(10L, "Rain - SID", listOf("piano", "bass"), "2026.10.21 14:00")
        WorkStore.add(ctx, w)
        assertEquals(listOf(w), WorkStore.load(ctx))
    }

    @Test
    fun add_sameIdTwice_keepsOneEntry() {
        val a = Work(1L, "A", listOf("piano"), "d1")
        val b = Work(2L, "B", listOf("drums"), "d2")
        WorkStore.add(ctx, a)
        WorkStore.add(ctx, b)
        WorkStore.add(ctx, a.copy(title = "A2"))
        assertEquals(listOf("A2", "B"), WorkStore.load(ctx).map { it.title })
    }

    @Test
    fun corruptedPreference_doesNotCrash() {
        ctx.getSharedPreferences("rocky", Context.MODE_PRIVATE).edit()
            .putString(workKey(1L), "broken line\n\n1\tOK\tpiano\td").commit()
        assertEquals(listOf("OK"), WorkStore.load(ctx).map { it.title })
    }

    @Test
    fun eachUser_hasOwnStorage() {
        WorkStore.add(ctx, Work(1L, "User1 song", listOf("piano"), "d"))
        loginAs(2L)
        assertTrue(WorkStore.load(ctx).isEmpty())                 // 다른 회원에게는 안 보임
        WorkStore.add(ctx, Work(2L, "User2 song", listOf("bass"), "d"))
        loginAs(1L)
        assertEquals(listOf("User1 song"), WorkStore.load(ctx).map { it.title })
    }

    @Test
    fun demoKor_usesKoreanNames() {
        assertEquals(listOf("피아노", "드럼", "베이스", "기타"), Demo.INSTRUMENTS.map { Demo.kor(it) })
    }
}
