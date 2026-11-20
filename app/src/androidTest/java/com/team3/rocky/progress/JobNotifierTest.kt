// AI-generated with Claude Code, 2026-11-20
package com.team3.rocky.progress

import android.Manifest
import android.app.NotificationManager
import android.content.Context
import android.net.Uri
import android.os.Build
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** 앱 밖에 있을 때 보내는 완성·실패 알림 */
@RunWith(AndroidJUnit4::class)
class JobNotifierTest {
    private val ctx: Context = ApplicationProvider.getApplicationContext()
    private val manager = ctx.getSystemService(NotificationManager::class.java)
    private lateinit var job: ScoreJob

    private fun shown() = manager.activeNotifications.any { it.id == (job.id % Int.MAX_VALUE).toInt() }

    private fun waitShown(expected: Boolean) {
        repeat(40) { if (shown() == expected) return; Thread.sleep(100) }
    }

    @Before fun setUp() {
        if (Build.VERSION.SDK_INT >= 33) {
            InstrumentationRegistry.getInstrumentation().uiAutomation
                .grantRuntimePermission(ctx.packageName, Manifest.permission.POST_NOTIFICATIONS)
        }
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            job = ScoreJob(System.currentTimeMillis(), "알림 곡", listOf("drums"), emptyList(), AudioFile(Uri.EMPTY, "a.mp3"))
        }
    }

    @After fun tearDown() = JobNotifier.clear(ctx, job)

    @Test fun readyIsShownAndClearRemovesIt() {
        assertFalse(JobNotifier.needsPermission(ctx))
        JobNotifier.ready(ctx, job)
        waitShown(true)
        assertTrue("완성 알림이 보여야 함", shown())
        JobNotifier.clear(ctx, job)
        waitShown(false)
        assertFalse(shown())
    }

    @Test fun stoppedReplacesTheSameSongsNotification() {
        JobNotifier.ready(ctx, job)
        JobNotifier.stopped(ctx, job, "깨진 파일일 수 있어요")
        waitShown(true)
        assertTrue(manager.activeNotifications.count { it.id == (job.id % Int.MAX_VALUE).toInt() } == 1)
    }
}
