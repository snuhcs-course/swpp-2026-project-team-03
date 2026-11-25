// AI-generated with Claude Code, 2026-11-25
package com.team3.rocky.server

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/** 듣기용 MP3는 완성 후 24시간만 (베타 저장 공간). 그 뒤에는 재생할 파일이 없고 악보·MIDI는 남는다. */
class AudioExpiryTest {
    @get:Rule val tmp = TemporaryFolder()

    private val json = """{"id":"abc","title":"t","full_band":{"pdf":"scores/full_band.pdf","midi":"full_score.mid",
        "mp3":"scores/band.mp3"},"instruments":{"bass":{"pdf":"scores/bass.pdf","midi":"scores/bass.mid","mp3":"scores/bass.mp3"}},
        "original_parts":["bass"],"generated_parts":[],"audio_expires_at":1764000000.5}"""

    @Test fun serverExpiryIsReadAsMillisAndKeptOnThePhone() {
        val r = ApiJson.result(json)
        assertEquals(1_764_000_000_500L, r.audioExpiresAt)
        assertEquals(r.audioExpiresAt, ApiJson.result(ScoreStore.toJson(r)).audioExpiresAt)
    }

    @Test fun olderServerSendsNoExpiry() {
        assertNull(ApiJson.result(json.replace(""","audio_expires_at":1764000000.5""", "")).audioExpiresAt)
    }

    private fun score(until: Long): LocalScore {
        val dir = tmp.newFolder()
        for (f in listOf("scores/band.mp3", "scores/bass.mp3", "scores/bass.mid", "full_score.mid", "scores/bass.pdf")) {
            java.io.File(dir, f).apply { parentFile!!.mkdirs(); writeText("x") }
        }
        return LocalScore(dir, ApiJson.result(json), 0, until)
    }

    @Test fun playsWithin24Hours() {
        val s = score(System.currentTimeMillis() + 60_000)
        assertTrue(s.audioAvailable())
        assertEquals("bass.mp3", s.audio("bass")!!.name)
        assertNotNull(s.audio(null))
    }

    @Test fun after24HoursThereIsNothingToPlayButTheScoreStays() {
        val s = score(System.currentTimeMillis() - 1)
        assertFalse(s.audioAvailable())
        assertNull(s.audio("bass"))   // MIDI로 대신 재생하지도 않는다 (재생 바를 숨긴다)
        assertNull(s.mp3(null))
        assertNotNull(s.pdf("bass"))
        assertNotNull(s.midi("bass"))
    }

    @Test fun dropAudioRemovesEveryMp3OnlyInThatSong() {
        val root = tmp.newFolder()
        val keep = listOf("scores/bass.pdf", "scores/bass.mid", "transpositions/+2/scores/bass.pdf")
        val gone = listOf("scores/bass.mp3", "transpositions/+2/scores/band.mp3")
        (keep + gone).forEach { java.io.File(root, it).apply { parentFile!!.mkdirs(); writeText("x") } }
        ScoreStore.dropAudio(root)
        keep.forEach { assertTrue(it, java.io.File(root, it).isFile) }
        gone.forEach { assertFalse(it, java.io.File(root, it).exists()) }
    }

    @Test fun phoneFallsBackTo24HoursAfterDownloadWhenTheServerIsOld() {
        val root = tmp.newFolder()
        val original = java.io.File(root, "result.json")
        original.writeText(json.replace(""","audio_expires_at":1764000000.5""", ""))
        original.setLastModified(1_000_000L)
        val until = ScoreStore.audioUntil(root, ApiJson.result(original.readText()))
        assertEquals(1_000_000L + ScoreStore.AUDIO_TTL_MS, until)
    }
}
