// AI-generated with Claude Code, 2026-11-20
package com.team3.rocky

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** 올릴 수 있는 곡 파일 형식 (MP3·WAV·FLAC·OGG) */
class AudioFormatsTest {
    @Test fun acceptsTheFourFormatsInAnyCase() {
        listOf("song.mp3", "song.WAV", "라이브.flac", "a.b.Ogg").forEach { assertTrue(it, isSupportedAudio(it)) }
    }

    @Test fun rejectsOtherFilesAndNamesWithoutExtension() {
        listOf("score.pdf", "sheet.xlsx", "voice.m4a", "mp3", "song.", "").forEach { assertFalse(it, isSupportedAudio(it)) }
    }

    @Test fun pickerOffersEveryAcceptedFormat() {
        listOf("audio/mpeg", "audio/wav", "audio/flac", "audio/ogg").forEach { assertTrue(it, it in PICK_TYPES) }
    }
}
