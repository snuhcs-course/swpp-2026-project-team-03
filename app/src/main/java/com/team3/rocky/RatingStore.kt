// AI-generated with Claude Code, 2026-11-09
package com.team3.rocky

import android.content.Context

/**
 * 결과 악보에 매긴 별점(1~5)을 휴대폰에 저장한다. 나중에 악보 품질을 개선할 때 쓰려고 모은다.
 *
 * 지금은 서버에 받는 곳이 없어서 앱 안에만 남긴다. 서버로 보낼 때 필요한 곡 이름·악기·시간도
 * 같이 적어 두고, 아직 안 보낸 것은 [unsent]로 꺼낼 수 있게 한다.
 */
object RatingStore {
    private const val PREF = "rocky_ratings"

    data class Rating(
        val workId: Long,
        val title: String,
        val instruments: List<String>,
        val stars: Int,
        val ratedAt: Long,
        val sent: Boolean = false,
    )

    private fun key(workId: Long) = "w_$workId"

    /** 이 악보에 매긴 별점. 아직 안 매겼으면 0. */
    fun stars(ctx: Context, workId: Long): Int =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(key(workId), null)
            ?.let { decode(workId, it)?.stars } ?: 0

    /** 별점을 저장한다. 다시 누르면 바뀐 별점으로 덮어쓰고, 다시 보내야 하는 것으로 표시한다. */
    fun rate(ctx: Context, work: Work, stars: Int, now: Long = System.currentTimeMillis()) {
        val r = Rating(work.id, work.title, work.instruments, stars.coerceIn(1, 5), now)
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString(key(work.id), encode(r)).apply()
    }

    /** 아직 서버로 보내지 않은 별점 (서버에 받는 곳이 생기면 사용). */
    fun unsent(ctx: Context): List<Rating> =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).all.mapNotNull { (k, v) ->
            val id = k.removePrefix("w_").toLongOrNull() ?: return@mapNotNull null
            (v as? String)?.let { decode(id, it) }
        }.filter { !it.sent }

    // 한 줄: 별점 \t 시간 \t 보냄(0/1) \t 악기(쉼표) \t 곡 이름
    internal fun encode(r: Rating): String =
        listOf(r.stars, r.ratedAt, if (r.sent) 1 else 0, r.instruments.joinToString(","), r.title.replace("\t", " "))
            .joinToString("\t")

    internal fun decode(workId: Long, s: String): Rating? {
        val p = s.split("\t", limit = 5)
        if (p.size < 5) return null
        val stars = p[0].toIntOrNull()?.takeIf { it in 1..5 } ?: return null
        return Rating(
            workId = workId,
            title = p[4],
            instruments = p[3].split(",").filter { it.isNotBlank() },
            stars = stars,
            ratedAt = p[1].toLongOrNull() ?: 0L,
            sent = p[2] == "1",
        )
    }
}
