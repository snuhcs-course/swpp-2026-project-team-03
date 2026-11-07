package com.team3.rocky.progress

import org.junit.Assert.assertEquals
import org.junit.Test

/** 앱의 밴드 구성 → 서버(unified.py --requested)로 보내는 악기 이름 */
class ScoreJobsMappingTest {
    @Test fun twoGuitarsAreSentAsOneGuitar() {
        assertEquals(listOf("piano", "drums", "guitar"),
            ScoreJobs.requestedParts(listOf("piano", "drums", "guitar", "guitar2")))
    }

    @Test fun vocalIsNotSent() {
        assertEquals(listOf("bass"), ScoreJobs.requestedParts(listOf("vocal", "bass")))
    }

    @Test fun serverOriginalMarksSecondGuitarAsOriginal() {
        // 서버가 원곡에 기타·드럼이 있다고 하면, 우리 밴드의 기타 2도 원곡 파트(AI 생성 아님)
        assertEquals(listOf("drums", "guitar", "guitar2"),
            ScoreJobs.originalFromServer(listOf("piano", "drums", "guitar", "guitar2"), listOf("guitar", "drums")))
    }

    @Test fun aiMadeSecondGuitarIsMarkedAsGenerated() {
        // 원곡 기타 1대 + 우리 밴드 기타 2대: AI가 기타 2를 만들면 결과에 guitar_1/guitar_2가 따로 온다 → 기타 2는 ✨
        val original = ScoreJobs.originalFromServer(
            listOf("drums", "guitar", "guitar2"), listOf("drums", "guitar"),
            generated = emptyList(), resultParts = listOf("drums", "guitar_1", "guitar_2"),
        )
        assertEquals(listOf("drums", "guitar"), original)
        assertEquals(listOf("drums", "guitar"),
            ScoreJobs.originalFromServer(listOf("drums", "guitar", "guitar2"), listOf("drums", "guitar"), generated = listOf("guitar_2")))
    }

    @Test fun generatedPartsAreNotOriginal() {
        assertEquals(listOf("drums"),
            ScoreJobs.originalFromServer(listOf("piano", "drums"), listOf("drums", "piano"), generated = listOf("piano")))
    }

    @Test fun serverOriginalWithoutGuitar() {
        assertEquals(listOf("drums"), ScoreJobs.originalFromServer(listOf("guitar", "guitar2"), listOf("drums")))
    }
}
