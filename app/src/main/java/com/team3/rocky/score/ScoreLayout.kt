package com.team3.rocky.score

import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * 악보 한 줄(시스템): 함께 연주하는 보표들과 그 안의 마디선.
 * 좌표는 페이지 그림의 픽셀. [bars]는 각 마디의 오른쪽 마디선 x이므로 마디 수 = bars.size.
 */
data class StaffSystem(val top: Int, val bottom: Int, val left: Int, val right: Int, val bars: List<Int>)

/**
 * 렌더링한 악보 페이지에서 줄과 마디선을 찾는다.
 * PDF에는 마디 위치 정보가 없어서 그림을 읽는다: 오선(가로로 긴 줄 5개, TAB은 6개)을 찾고,
 * 왼쪽 끝 세로줄로 이어진 보표를 한 줄로 묶고, 보표 높이를 꽉 채우되 위아래로 튀어나오지 않는
 * 세로줄을 마디선으로 센다 (음표 기둥은 보표 밖으로 나온다).
 * MuseScore 밴드 악보와 alphaTab 기타·베이스 TAB에서 확인했다. 틀릴 수 있으므로
 * [MeasureLayout]이 MIDI 마디 수와 맞춰 보고, 다르면 쓰지 않는다.
 */
object ScoreLayout {
    private class Line(val y: Double, val x0: Int, val x1: Int)
    private class Staff(val top: Double, val bottom: Double, val space: Double, val x0: Int, val x1: Int, val lines: Int)

    /** [pixels]는 ARGB (Bitmap.getPixels 그대로), 크기 [width]×[height]. */
    fun systems(pixels: IntArray, width: Int, height: Int): List<StaffSystem> {
        val dark = BooleanArray(pixels.size) { i ->
            val p = pixels[i]
            val a = p ushr 24
            val lum = (((p shr 16) and 0xFF) * 3 + ((p shr 8) and 0xFF) * 6 + (p and 0xFF)) / 10
            a > 128 && lum < 200
        }
        val page = Page(dark, width, height)
        val staves = staves(page.staffLines())
        return group(page, staves).map { sys -> StaffSystem(
            top = sys.first().top.roundToInt(), bottom = sys.last().bottom.roundToInt(),
            left = sys.minOf { it.x0 }, right = sys.maxOf { it.x1 }, bars = barlines(page, sys),
        ) }
    }

    private class Page(val dark: BooleanArray, val w: Int, val h: Int) {
        fun at(x: Int, y: Int) = x in 0 until w && y in 0 until h && dark[y * w + x]

        /** 열 x에서 행 [y0, y1) 중 어두운 비율 */
        fun colFrac(x: Int, y0: Int, y1: Int): Double {
            val a = max(0, y0)
            val b = min(h, y1)
            if (b <= a) return 0.0
            var n = 0
            for (y in a until b) if (dark[y * w + x]) n++
            return n.toDouble() / (b - a)
        }

        fun staffLines(): List<Line> {
            val gap = (0.04 * w).toInt()
            val out = mutableListOf<Line>()
            var runStart = -1
            var runEnd = -1
            val segs = mutableListOf<Pair<Int, Int>>()
            fun flush() {
                if (runStart >= 0) {
                    out += Line((runStart + runEnd) / 2.0, segs.map { it.first }.sorted()[segs.size / 2],
                        segs.map { it.second }.sorted()[segs.size / 2])
                }
                runStart = -1; segs.clear()
            }
            for (y in 0 until h) {
                val seg = longestSegment(y, gap)
                val ok = seg != null && seg.second - seg.first >= 0.12 * w && darkFrac(y, seg) >= 0.7
                if (ok) {
                    if (runStart >= 0 && y - runEnd > 1) flush()
                    if (runStart < 0) runStart = y
                    runEnd = y
                    segs += seg!!
                } else if (runStart >= 0 && y - runEnd > 1) {
                    flush()
                }
            }
            flush()
            return out
        }

        /** 가장 긴 어두운 구간. TAB 줄은 숫자에 끊기므로 [gap]px 이하의 틈은 잇는다. */
        private fun longestSegment(y: Int, gap: Int): Pair<Int, Int>? {
            var best: Pair<Int, Int>? = null
            var start = -1
            var prev = -1
            val row = y * w
            for (x in 0 until w) {
                if (!dark[row + x]) continue
                if (start < 0) start = x
                else if (x - prev > gap) {
                    if (best == null || prev - start > best.second - best.first) best = start to prev
                    start = x
                }
                prev = x
            }
            if (start >= 0 && (best == null || prev - start > best.second - best.first)) best = start to prev
            return best
        }

        private fun darkFrac(y: Int, seg: Pair<Int, Int>): Double {
            var n = 0
            for (x in seg.first..seg.second) if (dark[y * w + x]) n++
            return n.toDouble() / (seg.second - seg.first + 1)
        }
    }

    /** 간격이 같은 오선 5줄(TAB 6줄)을 보표로 묶는다. */
    private fun staves(lines: List<Line>): List<Staff> {
        val out = mutableListOf<Staff>()
        var i = 0
        while (i < lines.size) {
            val found = listOf(6, 5).firstNotNullOfOrNull { n ->
                if (i + n > lines.size) return@firstNotNullOfOrNull null
                val g = lines.subList(i, i + n)
                val d = g.zipWithNext { a, b -> b.y - a.y }
                val mean = d.average()
                val mx0 = g.map { it.x0 }.sorted()[n / 2]
                val mx1 = g.map { it.x1 }.sorted()[n / 2]
                val same = g.count { abs(it.x0 - mx0) <= mean && abs(it.x1 - mx1) <= mean }
                // 6줄은 모두 같은 길이여야 TAB으로 본다 (5줄 위의 빔 같은 가짜 줄을 막는다).
                val ok = d.min() > 3 && d.max() - d.min() <= max(2.0, 0.15 * mean) && same >= (if (n == 6) n else n - 1)
                if (ok) Staff(g.first().y, g.last().y, mean, mx0, mx1, n) else null
            }
            if (found != null) { out += found; i += found.lines } else i++
        }
        return out
    }

    /** 왼쪽 끝에서 세로줄로 이어진 보표끼리 한 줄로 묶는다. */
    private fun group(page: Page, staves: List<Staff>): List<List<Staff>> {
        val out = mutableListOf<MutableList<Staff>>()
        for (s in staves) {
            val p = out.lastOrNull()?.last()
            if (p != null) {
                val y0 = p.bottom.toInt() + 2
                val y1 = s.top.toInt() - 2
                val x0 = min(p.x0, s.x0)
                val joined = y1 > y0 && (max(0, x0 - (4 * s.space).toInt()) until min(page.w, x0 + s.space.toInt()))
                    .any { page.colFrac(it, y0, y1) > 0.9 }
                if (joined) { out.last() += s; continue }
            }
            out += mutableListOf(s)
        }
        return out
    }

    private fun barlines(page: Page, sys: List<Staff>): List<Int> {
        val space = sys.map { it.space }.average()
        val x0 = sys.minOf { it.x0 }
        val x1 = sys.maxOf { it.x1 }
        val m = max(2, (0.6 * space).toInt())
        val votes = IntArray(page.w)
        sys.forEachIndexed { k, s ->
            val top = s.top.roundToInt()
            val bot = s.bottom.roundToInt()
            // 오선 줄을 뺀 보표 안쪽 행: 박자표·음자리표 같은 덩어리 글자를 가려낼 때 쓴다.
            val rows = (top..bot).filter { y -> (0 until s.lines).all { j -> abs(y - (s.top + j * s.space)) > 1.5 } }
            val side = max(2, (0.3 * s.space).toInt())
            fun body(xa: Int, xb: Int): Double {
                val a = max(0, xa)
                val b = min(page.w, xb)
                if (b <= a || rows.isEmpty()) return 0.0
                var n = 0
                for (x in a until b) for (y in rows) if (page.at(x, y)) n++
                return n.toDouble() / ((b - a) * rows.size)
            }
            for (x in max(0, x0 - 2)..min(page.w - 1, x1 + 2)) {
                if (page.colFrac(x, top, bot + 1) < 0.95) continue
                // 마디선은 가는 줄이라 양옆이 비어 있다. 양쪽이 다 차 있으면 박자표(3/4의 숫자) 같은 글자다.
                if (body(x - side - 1, x - 1) > 0.4 && body(x + 2, x + side + 2) > 0.4) continue
                // 보표 위아래로 튀어나오면 음표 기둥. 위아래 보표까지 이어진 마디선(피아노 큰보표)은 괜찮다.
                val above = page.colFrac(x, top - m, top - 1) < 0.75 ||
                    (k > 0 && page.colFrac(x, sys[k - 1].bottom.roundToInt() + 1, top) >= 0.95)
                val below = page.colFrac(x, bot + 2, bot + m) < 0.75 ||
                    (k + 1 < sys.size && page.colFrac(x, bot + 1, sys[k + 1].top.roundToInt()) >= 0.95)
                if (above && below) votes[x]++
            }
        }
        val need = if (sys.size <= 2) sys.size else ceil(0.6 * sys.size).toInt()
        val centers = mutableListOf<Int>()
        var groupStart = -1
        var groupEnd = -1
        for (x in votes.indices) {
            if (votes[x] < need) continue
            if (groupStart >= 0 && x - groupEnd > 1.5 * space) {
                centers += (groupStart + groupEnd) / 2
                groupStart = -1
            }
            if (groupStart < 0) groupStart = x
            groupEnd = x
        }
        if (groupStart >= 0) centers += (groupStart + groupEnd) / 2
        // 줄 맨 앞의 세로줄은 마디의 끝이 아니다.
        return centers.filter { it > x0 + 1.5 * space }
    }
}
