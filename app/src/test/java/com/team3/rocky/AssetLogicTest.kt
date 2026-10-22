package com.team3.rocky

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** U5–U7: 데모 결과 파일 찾기, 악보 페이지 순서, 이름·형식 변환 (순수 로직) */
class AssetLogicTest {

    // U5
    @Test
    fun findAsset_fallsBackToNextExtension() {
        val files = listOf("band.flac", "band.pdf")
        assertEquals("band.flac", findAsset(files, "band", AUDIO_EXT))
    }

    @Test
    fun findAsset_prefersEarlierExtension() {
        val files = listOf("band.wav", "band.mp3")
        assertEquals("band.mp3", findAsset(files, "band", AUDIO_EXT))
    }

    @Test
    fun findAsset_returnsNullWhenMissing() {
        assertNull(findAsset(listOf("piano.mp3", "band.pdf"), "band", AUDIO_EXT))
        assertNull(findAsset(emptyList(), "band", AUDIO_EXT))
    }

    @Test
    fun findAsset_findsInstrumentAudio() {
        val files = listOf("band.mp3", "bass.mp3", "drums.wav")
        assertEquals("bass.mp3", findAsset(files, "bass", AUDIO_EXT))
        assertEquals("drums.wav", findAsset(files, "drums", AUDIO_EXT))
    }

    // U6
    @Test
    fun scorePageFiles_sortsNumerically() {
        val files = listOf("band-10.png", "band-2.png", "band-1.png", "band.mid", "piano.png", "band-3.png")
        assertEquals(
            listOf("band-1.png", "band-2.png", "band-3.png", "band-10.png"),
            scorePageFiles(files, "band"),
        )
    }

    @Test
    fun scorePageFiles_singlePageAndOtherImageTypes() {
        assertEquals(listOf("band.png"), scorePageFiles(listOf("band.png", "band.pdf"), "band"))
        assertEquals(listOf("band-1.jpg", "band-2.webp"), scorePageFiles(listOf("band-2.webp", "band-1.jpg"), "band"))
    }

    @Test
    fun scorePageFiles_ignoresSimilarNames() {
        val files = listOf("bandit.png", "my-band-1.png", "band-1.png.bak", "band-x.png")
        assertTrue(scorePageFiles(files, "band").isEmpty())
    }

    @Test
    fun scorePageFiles_perInstrument_onlyThatInstrument() {
        // 결과 화면에서 악기를 누르면 그 악기 악보만 보여요 (Iteration 2 추가 기능)
        val files = listOf("band-1.png", "bass-2.png", "bass-1.png", "drums-1.png", "bass.mp3")
        assertEquals(listOf("bass-1.png", "bass-2.png"), scorePageFiles(files, "bass"))
        assertTrue(scorePageFiles(files, "piano").isEmpty())
    }

    // 내보내기 목록
    @Test
    fun exportFiles_listsOnlyExistingFiles() {
        assertEquals(
            listOf("band.pdf" to "밴드 악보", "band.mid" to "밴드 MIDI"),
            exportFiles(listOf("band.mid", "band.pdf", "band.png"), "band"),
        )
        assertEquals(listOf("band.mid" to "밴드 MIDI"), exportFiles(listOf("band.mid"), "band"))
        assertTrue(exportFiles(emptyList(), "band").isEmpty())
    }

    // U7
    @Test
    fun korName_mapsInstruments() {
        assertEquals("피아노", korName("piano"))
        assertEquals("드럼", korName("drums"))
        assertEquals("베이스", korName("bass"))
        assertEquals("기타", korName("guitar"))
        assertEquals("synth", korName("synth"))
    }

    @Test
    fun mimeOf_byExtension() {
        assertEquals("application/pdf", mimeOf("band.pdf"))
        assertEquals("audio/midi", mimeOf("band.mid"))
        assertEquals("audio/midi", mimeOf("BAND.MIDI"))
        assertEquals("image/png", mimeOf("band-1.png"))
        assertEquals("*/*", mimeOf("band.wav"))
        assertEquals("*/*", mimeOf("noextension"))
    }
}
