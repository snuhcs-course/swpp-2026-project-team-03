package com.team3.rocky.score

import org.json.JSONObject
import kotlin.math.roundToInt

/**
 * 서버가 악보를 그리면서 적어 둔 마디 위치 (scores/<파트>.measures.json, publish_scores.py).
 * 그림에서 마디선을 찾는 [ScoreLayout]과 달리 틀리지 않아서, 있으면 이것을 쓴다.
 * 좌표는 PDF 포인트이고 페이지 왼쪽 위가 (0, 0). 마디마다 상자가 하나 이상이다
 * (기타 두 대를 한 PDF에 그리면 대마다 하나).
 */
class PrintedMeasures(
    private val pageSizes: List<Pair<Double, Double>>,
    private val boxes: List<List<DoubleArray>>,  // [page, x, y, width, height]
) {
    val count: Int get() = boxes.size

    /**
     * 화면에 그린 페이지 그림의 픽셀 좌표로 바꾼다.
     * @param widths 페이지마다 PDF를 그린 폭(px, 여백을 자르기 전)
     * @param crops 페이지마다 여백을 잘라낸 만큼 (왼쪽, 위) px
     * 그리지 않은 페이지(앱은 앞 30쪽만 그린다)의 마디는 뺀다.
     */
    fun layout(widths: List<Int>, crops: List<Pair<Int, Int>>): MeasureLayout {
        val out = boxes.mapNotNull { list ->
            val b = list.first()
            val page = b[0].toInt()
            if (page !in widths.indices || page !in crops.indices || page !in pageSizes.indices) return@mapNotNull null
            val scale = widths[page] / pageSizes[page].first
            val (dx, dy) = crops[page]
            MeasureBox(
                page = page,
                top = (b[2] * scale).roundToInt() - dy,
                bottom = ((b[2] + b[4]) * scale).roundToInt() - dy,
                left = (b[1] * scale).roundToInt() - dx,
                right = ((b[1] + b[3]) * scale).roundToInt() - dx,
            )
        }
        return MeasureLayout(out, exact = true)
    }

    companion object {
        /** 형식이 다르면 null (그러면 그림에서 마디를 찾는다). */
        fun parse(text: String): PrintedMeasures? = runCatching {
            val o = JSONObject(text)
            require(o.optInt("version") == 1 && o.optString("unit") == "pt")
            val pages = o.getJSONArray("pages")
            val sizes = (0 until pages.length()).map { i ->
                val p = pages.getJSONArray(i)
                p.getDouble(0) to p.getDouble(1)
            }
            val measures = o.getJSONArray("measures")
            val boxes = (0 until measures.length()).map { i ->
                val list = measures.getJSONArray(i)
                require(list.length() > 0)
                (0 until list.length()).map { j ->
                    val b = list.getJSONArray(j)
                    DoubleArray(5) { k -> b.getDouble(k) }
                }
            }
            require(sizes.all { it.first > 0 } && boxes.isNotEmpty())
            PrintedMeasures(sizes, boxes)
        }.getOrNull()
    }
}
