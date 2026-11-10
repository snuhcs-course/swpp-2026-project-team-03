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

    @Test fun generatedSecondGuitarIsNotOriginal() {
        // 원곡 기타 1대인데 우리 밴드가 2대면 서버가 기타를 하나 만든다 → 기타 2는 AI 생성(✨)
        assertEquals(listOf("drums", "guitar"),
            ScoreJobs.originalFromServer(listOf("drums", "guitar", "guitar2"), listOf("guitar", "drums"),
                generated = listOf("guitar")))
    }

    @Test fun serverOriginalWithoutGuitar() {
        assertEquals(listOf("drums"), ScoreJobs.originalFromServer(listOf("guitar", "guitar2"), listOf("drums")))
    }
}
