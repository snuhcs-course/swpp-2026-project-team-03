// AI-generated with Claude Code, 2026-11-20
package com.team3.rocky

import android.content.Context
import android.net.Uri
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.PI
import kotlin.math.sin

/** 곡을 고르자마자 하는 확인: 정상 음원, 30초 이하, 깨진 파일, 음원이 아닌 파일 */
@RunWith(AndroidJUnit4::class)
class AudioCheckTest {
    private val ctx: Context = ApplicationProvider.getApplicationContext()

    /** [seconds]초 길이의 8 kHz 모노 16비트 WAV (440 Hz 사인파) */
    private fun wav(name: String, seconds: Int): Uri {
        val rate = 8000
        val samples = rate * seconds
        val data = ByteBuffer.allocate(samples * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (i in 0 until samples) data.putShort((sin(2 * PI * 440 * i / rate) * 8000).toInt().toShort())
        val h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        h.put("RIFF".toByteArray()).putInt(36 + samples * 2).put("WAVE".toByteArray())
        h.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(1).putInt(rate).putInt(rate * 2).putShort(2).putShort(16)
        h.put("data".toByteArray()).putInt(samples * 2)
        val f = File(ctx.cacheDir, name)
        f.writeBytes(h.array() + data.array())
        return Uri.fromFile(f)
    }

    private fun file(name: String, bytes: ByteArray): Uri =
        Uri.fromFile(File(ctx.cacheDir, name).apply { writeBytes(bytes) })

    @Test fun longEnoughSongIsOk() {
        assertEquals(AudioCheck.Result.Ok, AudioCheck.check(ctx, wav("long.wav", 35)))
    }

    @Test fun shortSongReportsItsLength() {
        assertEquals(AudioCheck.Result.TooShort(10), AudioCheck.check(ctx, wav("short.wav", 10)))
    }

    @Test fun exactlyThirtySecondsIsTooShort() {
        assertEquals(AudioCheck.Result.TooShort(30), AudioCheck.check(ctx, wav("thirty.wav", 30)))
    }

    @Test fun spreadsheetRenamedToMp3IsBroken() {
        val zip = byteArrayOf(0x50, 0x4B, 0x03, 0x04) + ByteArray(4000) { (it * 31).toByte() }
        assertEquals(AudioCheck.Result.Broken, AudioCheck.check(ctx, file("sheet.mp3", zip)))
    }

    @Test fun emptyOrMissingFileIsBroken() {
        assertEquals(AudioCheck.Result.Broken, AudioCheck.check(ctx, file("empty.wav", ByteArray(0))))
        assertEquals(AudioCheck.Result.Broken, AudioCheck.check(ctx, Uri.fromFile(File(ctx.cacheDir, "nothing-here.mp3"))))
    }
}
