// AI-generated with Claude Code, 2026-11-21
package com.team3.rocky.progress

import com.team3.rocky.server.ApiJson
import com.team3.rocky.server.LocalScore
import com.team3.rocky.server.ScoreStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * 원곡에 기타가 없는데 우리 밴드가 기타 2대인 곡 (PR #29):
 * 파이프라인 manifest guitars_delivered=1 → 서버 결과 → 앱이 읽고, 폰에 저장했다 다시 읽어도 남고,
 * 결과 화면 안내(LocalScore.oneGuitarOnly)를 켜고, 보관함에는 기타 1대 곡으로 저장한다.
 */
class OneGuitarOnlyTest {
    private fun serverResult(delivered: String) = """
        {"id":"job1","title":"Hype Boy",
         "full_band":{"pdf":"scores/full.pdf","midi":"scores/full.mid","mp3":"scores/full.mp3"},
         "instruments":{"guitar":{"pdf":"scores/guitar.pdf","midi":"scores/guitar.mid"},
                        "bass":{"pdf":"scores/bass.pdf"},"piano":{"pdf":"scores/piano.pdf"},
                        "drums":{"pdf":"scores/drums.pdf"}},
         "original_parts":["bass","drums","piano"],"generated_parts":["guitar"],"faint_parts":[],
         "original_guitars":0$delivered}
    """.trimIndent()

    private val band = listOf("piano", "drums", "bass", "guitar", "guitar2")

    @Test fun noGuitarInSongButTwoInBandShowsNoticeAndSavesOneGuitar() {
        val result = ApiJson.result(serverResult(""","guitars_delivered":1"""))
        assertEquals(1, result.guitarsDelivered)
        // 폰의 result.json으로 저장했다가 다시 열어도 그대로
        val reopened = ApiJson.result(ScoreStore.toJson(result))
        assertEquals(1, reopened.guitarsDelivered)
        assertTrue(LocalScore(File("unused"), reopened).oneGuitarOnly)          // 결과 화면 안내
        assertTrue(ScoreJobs.oneGuitarOnly(band, reopened))
        assertEquals(listOf("piano", "drums", "bass", "guitar"),
            ScoreJobs.savedInstruments(band, ScoreJobs.oneGuitarOnly(band, reopened)))  // 기타 2 칸 없음
        // 기타는 AI가 만든 파트(✨)
        assertEquals(listOf("drums", "bass", "piano").sorted(),
            ScoreJobs.originalFromServer(band, reopened.originalParts, reopened.generatedParts).sorted())
    }

    @Test fun ordinaryResultHasNoNotice() {
        val result = ApiJson.result(serverResult(""","guitars_delivered":null"""))
        assertNull(result.guitarsDelivered)
        assertNull(ApiJson.result(ScoreStore.toJson(result)).guitarsDelivered)
        assertFalse(LocalScore(File("unused"), result).oneGuitarOnly)
        assertFalse(ScoreJobs.oneGuitarOnly(band, result))
        assertEquals(band, ScoreJobs.savedInstruments(band, false))
        // 예전 서버처럼 키가 아예 없어도
        assertNull(ApiJson.result(serverResult("")).guitarsDelivered)
    }

    @Test fun oneGuitarBandIsNotChanged() {
        val result = ApiJson.result(serverResult(""","guitars_delivered":1"""))
        val oneGuitar = listOf("drums", "bass", "guitar")
        assertFalse(ScoreJobs.oneGuitarOnly(oneGuitar, result))
        assertEquals(oneGuitar, ScoreJobs.savedInstruments(oneGuitar, false))
    }
}
