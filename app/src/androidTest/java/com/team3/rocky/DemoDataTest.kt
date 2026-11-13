// AI-generated with Claude Code, 2026-11-06
package com.team3.rocky

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Storage (WorkStore) and the dark-mode setting, on a device. (The bundled demo files were removed on 2026-11-11.) */
@RunWith(AndroidJUnit4::class)
class DemoDataTest {
    private val ctx = ApplicationProvider.getApplicationContext<Context>()

    private fun clearStorage() =
        ctx.getSharedPreferences("rocky", Context.MODE_PRIVATE).edit().clear().commit()

    @Before fun setUp() { clearStorage() }

    @After fun tearDown() {
        clearStorage()
        AppSettings.setDark(ctx, true)
    }

    @Test fun savedWorksComeBackNewestFirstAndCanBeRenamedAndRemoved() {
        val first = Work(1, "Song A", listOf("guitar", "bass"), "2026.11.06 10:00", original = listOf("guitar"))
        val second = Work(2, "Song\tB\nline", listOf("drums"), "2026.11.06 11:00")
        WorkStore.add(ctx, first)
        WorkStore.add(ctx, second)

        val loaded = WorkStore.load(ctx)
        assertEquals(listOf(2L, 1L), loaded.map { it.id })
        assertEquals("Song B line", loaded[0].title)               // tab and line break do not break the format
        assertEquals(listOf("guitar", "bass"), loaded[1].instruments)
        assertEquals(listOf("guitar"), loaded[1].original)
        assertTrue(loaded[0].original.isEmpty())

        WorkStore.add(ctx, first.copy(title = "Song A again"))     // same id: one entry, moved to the top
        assertEquals(listOf(1L, 2L), WorkStore.load(ctx).map { it.id })

        WorkStore.rename(ctx, 2, "Renamed")
        assertEquals("Renamed", WorkStore.load(ctx).first { it.id == 2L }.title)

        WorkStore.remove(ctx, 1)
        assertEquals(listOf(2L), WorkStore.load(ctx).map { it.id })
    }

    @Test fun soloPracticeWorkKeepsItsModeAndSongFile() {
        val solo = Work(7, "夜に駆ける", listOf("guitar"), "2026.11.13 23:00", personal = true, audio = "content://media/song/7")
        WorkStore.add(ctx, solo)
        WorkStore.add(ctx, Work(8, "Band song", listOf("drums", "bass"), "2026.11.13 23:01"))
        val loaded = WorkStore.load(ctx).associateBy { it.id }
        assertTrue(loaded.getValue(7).personal)
        assertEquals("content://media/song/7", loaded.getValue(7).audio)
        assertEquals("夜に駆ける", loaded.getValue(7).title)
        assertFalse(loaded.getValue(8).personal)
        assertEquals(null, loaded.getValue(8).audio)
    }

    @Test fun fileNamesAreMadeSafe() {
        assertEquals("a b c", safeFileName("a/b:c"))
        assertEquals("ROCKY", safeFileName("  "))
        assertEquals(60, safeFileName("x".repeat(80)).length)
    }

    @Test fun darkModeSettingIsSavedAndLoaded() {
        AppSettings.setDark(ctx, false)
        assertFalse(AppSettings.dark)
        AppSettings.setDark(ctx, true)
        AppSettings.load(ctx)
        assertTrue(AppSettings.dark)
    }
}
