// AI-generated with Claude Code, 2026-11-20
package com.team3.rocky

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.team3.rocky.server.ServerSettings
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** 별점·의견을 폰에 저장하고, 보낼 수 있으면 '보냄'으로 바꾸는지 */
@RunWith(AndroidJUnit4::class)
class RatingStoreDeviceTest {
    private val ctx: Context = ApplicationProvider.getApplicationContext()
    private val work = Work(id = 9_001, title = "별점 곡", instruments = listOf("drums"), date = "2026.11.20 18:00")

    private var oldUrl = ""
    private var oldKey = ""

    @Before fun clean() {
        oldUrl = ServerSettings.url(ctx)
        oldKey = ServerSettings.key(ctx)
        ctx.getSharedPreferences("rocky_ratings", Context.MODE_PRIVATE).edit().clear().commit()
    }

    /** 다른 테스트가 쓰는 서버 설정을 되돌린다. */
    @After fun restore() = ServerSettings.save(ctx, oldUrl, oldKey)

    private fun waitUntil(check: () -> Boolean) {
        repeat(50) { if (check()) return; Thread.sleep(100) }
    }

    @Test fun notRatedIsZeroAndStarsAreClamped() {
        ServerSettings.save(ctx, "", "")          // 서버 없음: 폰에만 남고 '안 보냄'
        assertEquals(0, RatingStore.stars(ctx, work.id))
        RatingStore.rate(ctx, work, 9)
        assertEquals(5, RatingStore.stars(ctx, work.id))
        RatingStore.rate(ctx, work, 0)
        assertEquals(1, RatingStore.stars(ctx, work.id))
        Thread.sleep(300)
        assertEquals(listOf(work.id), RatingStore.unsent(ctx).map { it.workId })
    }

    @Test fun ratingWithoutServerResultIsMarkedSent() {
        ServerSettings.save(ctx, "http://10.0.2.2:8000", "")
        RatingStore.rate(ctx, work, 4)
        waitUntil { RatingStore.unsent(ctx).isEmpty() }
        assertTrue(RatingStore.unsent(ctx).isEmpty())
        RatingStore.sendPending(ctx)
        assertEquals(4, RatingStore.stars(ctx, work.id))
    }

    @Test fun commentFinishesTheRatingPage() {
        ServerSettings.save(ctx, "", "")
        assertFalse(RatingStore.finished(ctx, work.id))
        RatingStore.comment(ctx, work, "   ")          // 의견 없이 제출해도 끝
        assertTrue(RatingStore.finished(ctx, work.id))
        RatingStore.rate(ctx, work, 3)
        RatingStore.comment(ctx, work.copy(id = 9_002), "좋아요")
        assertTrue(RatingStore.finished(ctx, 9_002))
    }
}
