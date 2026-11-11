package com.team3.rocky.band

import android.content.Context
import com.team3.rocky.Work
import com.team3.rocky.auth.AuthRepository
import com.team3.rocky.auth.User
import com.team3.rocky.server.MemberApi
import com.team3.rocky.server.MemberApiException
import com.team3.rocky.server.ScoreStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException

/**
 * ROCKY 서버의 밴드 DB (server/rocky_server/accounts.py). 다른 폰의 회원과 같은 밴드에 들어가고,
 * 공유한 악보는 서버의 작업 번호로 밴드원이 받는다. 로그인 토큰으로 누가 부르는지 서버가 안다.
 */
class ServerBandRepository(
    context: Context,
    private val api: () -> MemberApi = { MemberApi.from(context.applicationContext, AuthRepository.token(context)) },
) : BandRepository {
    private val ctx = context.applicationContext

    override suspend fun myBands(user: User): List<BandSummary> = io(emptyList()) {
        val a = JSONArray(api().get("/bands"))
        (0 until a.length()).map { i ->
            val o = a.getJSONObject(i)
            BandSummary(band(o.getJSONObject("band")), o.getInt("member_count"), o.getInt("score_count"), o.getString("my_instrument"))
        }
    }

    override suspend fun detail(bandId: Long): BandDetail? = io(null) {
        val o = JSONObject(api().get("/bands/$bandId"))
        val members = o.getJSONArray("members")
        val scores = o.getJSONArray("scores")
        BandDetail(
            band = band(o.getJSONObject("band")),
            members = (0 until members.length()).map { i ->
                val m = members.getJSONObject(i)
                BandMember(m.getLong("user_id"), m.getString("nickname"), m.getString("instrument"), m.getBoolean("is_owner"))
            },
            scores = (0 until scores.length()).map { i ->
                val s = scores.getJSONObject(i)
                SharedScore(
                    id = s.getLong("id"),
                    work = Work(
                        id = s.getLong("work_id"),
                        title = s.getString("title"),
                        instruments = MemberApi.strings(s.optJSONArray("instruments")),
                        date = s.optString("date"),
                        original = MemberApi.strings(s.optJSONArray("original")),
                    ),
                    sharedById = s.getLong("shared_by"),
                    sharedByName = s.getString("shared_by_name"),
                    sharedAt = s.getLong("shared_at"),
                    jobId = s.optString("job_id").takeIf { !s.isNull("job_id") && it.isNotBlank() },
                )
            },
        )
    }

    override suspend fun create(user: User, name: String, instrument: String): BandResult {
        BandRules.validateName(name)?.let { return BandResult.Failure(it) }
        return result { api().post("/bands", JSONObject().put("name", name.trim()).put("instrument", instrument)) }
    }

    override suspend fun join(user: User, code: String, instrument: String): BandResult {
        BandRules.validateCode(code)?.let { return BandResult.Failure(it) }
        return result {
            api().post("/bands/join", JSONObject().put("code", BandRules.normalizeCode(code)).put("instrument", instrument))
        }
    }

    override suspend fun leave(user: User, bandId: Long) = io(Unit) { api().post("/bands/$bandId/leave"); Unit }

    override suspend fun share(user: User, bandId: Long, work: Work): Boolean = io(false) {
        // 밴드원이 다른 폰에서 받을 수 있게 서버 작업 번호를 같이 올린다 (데모 곡은 없음).
        val jobId = ScoreStore.load(ctx, work.id)?.result?.id
        val body = JSONObject().put("work_id", work.id).put("title", work.title)
            .put("instruments", JSONArray(work.instruments)).put("date", work.date)
            .put("original", JSONArray(work.original)).put("job_id", jobId ?: JSONObject.NULL)
        JSONObject(api().post("/bands/$bandId/scores", body)).getBoolean("created")
    }

    override suspend fun rename(user: User, bandId: Long, name: String): BandResult {
        BandRules.validateName(name)?.let { return BandResult.Failure(it) }
        return result { api().patch("/bands/$bandId", JSONObject().put("name", name.trim())) }
    }

    override suspend fun renameScore(user: User, bandId: Long, scoreId: Long, title: String): Boolean = io(false) {
        if (title.isBlank()) return@io false
        api().patch("/bands/$bandId/scores/$scoreId", JSONObject().put("title", title.trim()))
        true
    }

    override suspend fun renameMyWork(userId: Long, workId: Long, title: String) = io(Unit) {
        api().patch("/me/works/$workId", JSONObject().put("title", title.trim()))
        Unit
    }

    /** 닉네임은 서버의 회원 정보 하나만 바꾸면 밴드에도 보인다. */
    override suspend fun updateNickname(user: User) = Unit

    override suspend fun isShared(userId: Long, workId: Long): Boolean = io(false) {
        JSONObject(api().get("/me/works/$workId/shared")).getBoolean("shared")
    }

    private fun band(o: JSONObject) = Band(
        id = o.getLong("id"), name = o.getString("name"), inviteCode = o.getString("invite_code"),
        ownerId = o.getLong("owner_id"), createdAt = o.getLong("created_at"),
    )

    /** 서버에 닿지 않거나 거절되면 [fallback]. 화면은 빈 목록·실패로 보여준다. */
    private suspend fun <T> io(fallback: T, block: () -> T): T = withContext(Dispatchers.IO) {
        try { block() } catch (e: IOException) { fallback } catch (e: org.json.JSONException) { fallback }
    }

    private suspend fun result(block: () -> String): BandResult = withContext(Dispatchers.IO) {
        try {
            BandResult.Success(band(JSONObject(block())))
        } catch (e: MemberApiException) {
            BandResult.Failure(e.message ?: com.team3.rocky.tr("요청을 처리하지 못했어요", "Couldn't do that"))
        } catch (e: IOException) {
            BandResult.Failure(
                com.team3.rocky.tr("서버에 연결하지 못했어요. 인터넷이나 연결 설정을 확인해 주세요", "Can't reach the server. Check the internet or connection settings"),
            )
        }
    }
}
