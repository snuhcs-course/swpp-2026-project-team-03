package com.team3.rocky.score

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File
import javax.imageio.ImageIO

/** 마디 기준 악보 넘기기: MIDI 마디 시간, 악보 그림의 마디선, 둘을 맞추는 규칙. */
class MeasureTest {
    private fun systems(file: File): List<StaffSystem> {
        val img = ImageIO.read(file)
        val px = img.getRGB(0, 0, img.width, img.height, null, 0, img.width)
        return ScoreLayout.systems(px, img.width, img.height)
    }

    private fun demo(name: String) = File("src/main/assets/demo/$name")
    private fun resource(name: String) = File(javaClass.classLoader!!.getResource("score/$name")!!.toURI())

    // ----- 악보 그림 → 줄과 마디 -----

    @Test fun museScoreBandPageHasThreeSystems() {
        // band-2.png: 10–12, 13–15, 16–19마디
        val s = systems(demo("band-2.png"))
        assertEquals(listOf(3, 3, 4), s.map { it.bars.size })
        assertTrue(s.zipWithNext().all { (a, b) -> a.bottom < b.top })
    }

    @Test fun lastPageWithShortFinalSystem() {
        // band-12.png: 89–95마디, 그리고 끝 마디 96 하나뿐인 짧은 줄
        assertEquals(listOf(7, 1), systems(demo("band-12.png")).map { it.bars.size })
    }

    @Test fun alphaTabGuitarTabPage() {
        // 오선과 TAB이 한 줄. 9–10, 11–13, 14, 15, 16, 17마디
        val s = systems(resource("alphatab-guitar-tab.png"))
        assertEquals(listOf(2, 3, 1, 1, 1, 1), s.map { it.bars.size })
    }

    @Test fun timeSignatureIsNotABarline() {
        // MuseScore 첫 페이지(3/4, 화면 너비 1080px): 첫 줄의 박자표 숫자를 마디선으로 세면 안 된다
        assertEquals(listOf(3, 3, 3), systems(resource("musescore-first-page-3-4.png")).map { it.bars.size })
    }

    @Test fun blankPageHasNoSystems() {
        assertTrue(ScoreLayout.systems(IntArray(200 * 300) { -1 }, 200, 300).isEmpty())
    }

    // ----- MIDI → 마디 시간 -----

    @Test fun demoMidiHas77MeasuresAt120Bpm() {
        val clock = MeasureClock.fromFile(demo("band.mid"))!!
        assertEquals(77, clock.count)  // band.mp3 is 154.6 s = 77 × 2 s
        assertEquals(0, clock.measureAt(0))
        assertEquals(0, clock.measureAt(1_999))
        assertEquals(1, clock.measureAt(2_000))
        assertEquals(76, clock.measureAt(999_999))
    }

    @Test fun tempoAndMeterChangesMoveMeasureStarts() {
        // 1–2마디 4/4 120 BPM(각 2초), 3마디부터 3/4 60 BPM(각 3초)
        val midi = smf(
            meta(0, 0x58, 4, 2, 24, 8), meta(0, 0x51, 0x07, 0xA1, 0x20),
            meta(960 * 8, 0x58, 3, 2, 24, 8), meta(0, 0x51, 0x0F, 0x42, 0x40),
            note(0), note(960 * 3 * 2 - 1),
            division = 960,
        )
        val clock = MeasureClock.parse(midi)!!
        assertEquals(listOf(0.0, 2000.0, 4000.0, 7000.0), clock.startsMs.toList())
        assertEquals(2, clock.measureAt(6_999))
        assertEquals(3, clock.measureAt(7_000))
    }

    @Test fun notMidiIsNull() {
        assertNull(MeasureClock.parse("RIFF....WAVE".toByteArray()))
        assertNull(MeasureClock.fromFile(File("no-such.mid")))
    }

    // ----- 둘을 맞추기 -----

    private fun sys(top: Int, vararg bars: Int) = StaffSystem(top, top + 50, 100, 1000, bars.toList())

    @Test fun detectedBarsAreUsedWhenCountMatchesMidi() {
        val layout = MeasureLayout.build(listOf(listOf(sys(0, 400, 700, 1000)), listOf(sys(0, 1000))), measures = 4)
        assertTrue(layout.exact)
        assertEquals(4, layout.count)
        assertEquals(MeasureBox(0, 0, 50, 400, 700), layout.box(1))
        assertEquals(1, layout.box(3)!!.page)
        assertEquals(layout.box(3), layout.box(99))  // past the end: last measure
    }

    @Test fun wrongBarCountFallsBackToEvenSplit() {
        // 마디선 3개를 찾았지만 MIDI는 8마디: 두 줄에 4마디씩, 칠할 때는 줄 전체
        val layout = MeasureLayout.build(listOf(listOf(sys(0, 400, 1000), sys(100, 1000))), measures = 8)
        assertFalse(layout.exact)
        assertEquals(8, layout.count)
        assertEquals(4, layout.boxes.count { it.top == 0 })
        assertEquals(MeasureBox(0, 100, 150, 100, 1000), layout.box(5))  // the whole second system
    }

    @Test fun noSystemsMeansNoLayout() {
        assertEquals(0, MeasureLayout.build(listOf(emptyList()), measures = 10).count)
        assertNull(MeasureLayout.build(emptyList(), measures = null).box(0))
    }

    // ----- 작은 MIDI 만들기 -----

    private fun vlq(v: Int): ByteArray {
        var x = v
        val out = mutableListOf(x and 0x7F)
        x = x shr 7
        while (x > 0) { out.add(0, (x and 0x7F) or 0x80); x = x shr 7 }
        return out.map { it.toByte() }.toByteArray()
    }

    private fun meta(delta: Int, type: Int, vararg data: Int) =
        vlq(delta) + byteArrayOf(0xFF.toByte(), type.toByte()) + vlq(data.size) + data.map { it.toByte() }.toByteArray()

    private fun note(delta: Int) = vlq(delta) + byteArrayOf(0x90.toByte(), 60, 100)

    private fun smf(vararg events: ByteArray, division: Int): ByteArray {
        val track = events.fold(ByteArray(0)) { a, b -> a + b } + byteArrayOf(0, 0xFF.toByte(), 0x2F, 0)
        val out = ByteArrayOutputStream()
        fun u16(v: Int) { out.write(v shr 8); out.write(v and 0xFF) }
        fun u32(v: Int) { u16(v ushr 16); u16(v and 0xFFFF) }
        out.write("MThd".toByteArray()); u32(6); u16(0); u16(1); u16(division)
        out.write("MTrk".toByteArray()); u32(track.size); out.write(track)
        return out.toByteArray()
    }
}
