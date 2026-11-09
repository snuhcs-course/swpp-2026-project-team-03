package com.team3.rocky.score

import java.io.File

/**
 * 재생 시간 → 몇 번째 마디인지. 악보와 함께 받은 MIDI의 템포와 박자표로 계산한다.
 * 결과 MP3는 같은 악보를 합성한 소리라서 0초가 1마디의 시작이다.
 * @param startsMs 각 마디가 시작하는 시간(ms), 오름차순
 */
class MeasureClock(val startsMs: DoubleArray) {
    val count: Int get() = startsMs.size

    /** [ms]에 연주 중인 마디 (0부터). */
    fun measureAt(ms: Long): Int {
        if (count == 0) return 0
        var lo = 0
        var hi = count - 1
        while (lo < hi) {
            val mid = (lo + hi + 1) / 2
            if (startsMs[mid] <= ms) lo = mid else hi = mid - 1
        }
        return lo
    }

    companion object {
        fun fromFile(file: File?): MeasureClock? =
            file?.takeIf { it.isFile }?.let { runCatching { parse(it.readBytes()) }.getOrNull() }

        /** Standard MIDI File을 읽는다. 마디가 하나도 없거나 형식이 다르면 null. */
        fun parse(bytes: ByteArray): MeasureClock? {
            val r = Reader(bytes)
            if (r.ascii(4) != "MThd") return null
            val headerLen = r.u32()
            r.u16()  // format
            val tracks = r.u16()
            val division = r.u16()
            if (division and 0x8000 != 0 || division == 0) return null  // SMPTE 시간은 쓰지 않는다
            r.pos = 8 + headerLen

            val tempos = mutableListOf<Pair<Long, Int>>()        // tick → 4분음표 길이(µs)
            val meters = mutableListOf<Triple<Long, Int, Int>>()  // tick → 박자 (분자, 분모)
            var lastTick = 0L
            repeat(tracks) {
                if (r.pos + 8 > bytes.size || r.ascii(4) != "MTrk") return@repeat
                val end = r.u32() + r.pos
                var tick = 0L
                var running = 0
                while (r.pos < end) {
                    tick += r.vlq()
                    var status = r.u8()
                    if (status < 0x80) { status = running; r.pos-- } // running status
                    when {
                        status == 0xFF -> {
                            val type = r.u8()
                            val len = r.vlq().toInt()
                            val at = r.pos
                            if (type == 0x51 && len == 3) tempos += tick to ((r.u8() shl 16) or (r.u8() shl 8) or r.u8())
                            if (type == 0x58 && len >= 2) meters += Triple(tick, r.u8(), 1 shl r.u8())
                            r.pos = at + len
                        }
                        status == 0xF0 || status == 0xF7 -> r.pos += r.vlq().toInt()
                        else -> {
                            running = status
                            val kind = status shr 4
                            r.pos += if (kind == 0xC || kind == 0xD) 1 else 2
                            if (kind == 0x8 || kind == 0x9) lastTick = maxOf(lastTick, tick)
                        }
                    }
                }
                r.pos = end
            }
            if (lastTick == 0L) return null
            tempos.sortBy { it.first }
            meters.sortBy { it.first }

            // 마디 시작 tick: 박자표는 마디 경계에서만 바뀐다고 본다.
            val starts = mutableListOf<Long>()
            var t = 0L
            var mi = 0
            var num = 4
            var den = 4
            while (t < lastTick) {
                while (mi < meters.size && meters[mi].first <= t) { num = meters[mi].second; den = meters[mi].third; mi++ }
                starts += t
                t += maxOf(1L, division.toLong() * 4 * num / den)
            }
            return MeasureClock(starts.map { msAt(it, tempos, division) }.toDoubleArray())
        }

        private fun msAt(tick: Long, tempos: List<Pair<Long, Int>>, division: Int): Double {
            var ms = 0.0
            var lastTick = 0L
            var us = 500_000  // 기본 120 BPM
            for ((at, tempo) in tempos) {
                if (at >= tick) break
                ms += (at - lastTick) * us / 1000.0 / division
                lastTick = at
                us = tempo
            }
            return ms + (tick - lastTick) * us / 1000.0 / division
        }
    }

    private class Reader(val b: ByteArray) {
        var pos = 0
        fun u8(): Int = b[pos++].toInt() and 0xFF
        fun u16(): Int = (u8() shl 8) or u8()
        fun u32(): Int = (u16() shl 16) or u16()
        fun ascii(n: Int) = String(b, pos, n, Charsets.US_ASCII).also { pos += n }
        fun vlq(): Long {
            var v = 0L
            while (true) {
                val c = u8()
                v = (v shl 7) or (c and 0x7F).toLong()
                if (c < 0x80) return v
            }
        }
    }
}
