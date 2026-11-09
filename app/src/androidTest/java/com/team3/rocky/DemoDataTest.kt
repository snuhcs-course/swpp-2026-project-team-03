// AI-generated with Claude Code, 2026-11-06
package com.team3.rocky

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Storage (WorkStore), bundled demo files (Assets) and the dark-mode setting, on a device. */
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

    @Test fun demoFilesAreFoundAndPagesAreInNumericOrder() {
        assertTrue("band.mp3" in Assets.list(ctx))
        assertEquals("band.mp3", Assets.find(ctx, "band", listOf("wav", "mp3")))
        assertNull(Assets.find(ctx, "band", listOf("ogg")))

        val pages = Assets.pages(ctx, "band")
        assertEquals((1..12).map { "band-$it.png" }, pages)       // band-2 before band-10
        assertEquals(listOf("bass-1.png", "bass-2.png", "bass-3.png"), Assets.pages(ctx, "bass"))
        assertTrue(Assets.pages(ctx, "nothing").isEmpty())
    }

    @Test fun demoFileIsCopiedToTheCache() {
        val copy = Assets.toCache(ctx, "band.mid", "copy.mid")
        val original = ctx.assets.open("demo/band.mid").use { it.readBytes() }
        assertTrue(copy.isFile)
        assertArrayEquals(original, copy.readBytes())
    }

    @Test fun scorePagesBecomeOnePdf() {
        val pdf = Assets.pagesToPdf(ctx, "bass", "bass-test.pdf")
        assertNotNull(pdf)
        val head = pdf!!.inputStream().use { it.readNBytesCompat(4) }
        assertEquals("%PDF", String(head, Charsets.US_ASCII))
        assertNull(Assets.pagesToPdf(ctx, "nothing", "none.pdf"))
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

    private fun java.io.InputStream.readNBytesCompat(n: Int): ByteArray {
        val buf = ByteArray(n)
        var off = 0
        while (off < n) {
            val r = read(buf, off, n - off)
            if (r < 0) break
            off += r
        }
        return buf.copyOf(off)
    }
}
