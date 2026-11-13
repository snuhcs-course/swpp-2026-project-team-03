// AI-generated with Claude Code, 2026-11-09
package com.team3.rocky

import android.content.Context
import com.team3.rocky.auth.AuthRepository
import com.team3.rocky.server.RockyApi
import com.team3.rocky.server.ScoreStore
import com.team3.rocky.server.ServerSettings
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.io.IOException

/**
 * 결과 악보에 매긴 별점(1~5). 악보 품질을 개선할 때 쓰려고 ROCKY 서버로 모은다 (PUT /jobs/{id}/rating,
 * 팀은 GET /ratings로 본다).
 *
 * 먼저 휴대폰에 저장하고 바로 서버로 보낸다. 인터넷이 안 되면 '안 보냄'으로 남겨 두었다가
 * 보관함을 열 때([sendPending]) 다시 보낸다.
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

    /** 별점을 저장하고 서버로 보낸다. 다시 누르면 바뀐 별점으로 덮어쓰고 다시 보낸다. */
    fun rate(ctx: Context, work: Work, stars: Int, now: Long = System.currentTimeMillis()) {
        val r = Rating(work.id, work.title, work.instruments, stars.coerceIn(1, 5), now)
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString(key(work.id), encode(r)).apply()
        val app = ctx.applicationContext
        scope.launch { send(app, r) }
    }

    /** 아직 서버로 못 보낸 별점을 다시 보낸다. */
    fun sendPending(ctx: Context) {
        val app = ctx.applicationContext
        scope.launch { unsent(app).forEach { send(app, it) } }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private fun send(ctx: Context, r: Rating) {
        if (!ServerSettings.isConfigured(ctx)) return
        // 서버의 곡 id는 폰에 받아 둔 결과(result.json)에 있다. 결과가 없으면 보낼 곳이 없다.
        val jobId = ScoreStore.load(ctx, r.workId)?.result?.id
        try {
            if (jobId != null) RockyApi.from(ctx).rate(jobId, r.stars, r.title, r.instruments, AuthRepository.token(ctx))
            markSent(ctx, r)
        } catch (e: IOException) {
            // 인터넷이 안 되거나 서버가 거절함: 다음에 다시 보낸다.
        }
    }

    /** 보낸 뒤에 사용자가 별점을 또 바꿨으면 그 새 별점은 '안 보냄'으로 남는다. */
    @Synchronized
    private fun markSent(ctx: Context, r: Rating) {
        val prefs = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val now = prefs.getString(key(r.workId), null)?.let { decode(r.workId, it) } ?: return
        if (now.stars == r.stars && now.ratedAt == r.ratedAt) prefs.edit().putString(key(r.workId), encode(now.copy(sent = true))).apply()
    }

    /** 아직 서버로 보내지 않은 별점. */
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
