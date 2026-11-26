// AI-generated with Claude Code, 2026-11-26
package com.team3.rocky.server

import android.content.Context
import com.team3.rocky.Work
import com.team3.rocky.WorkStore
import com.team3.rocky.auth.AuthRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * 보관함을 서버(/me/works)와 맞춘다. 서버 목록이 기준이라 어느 폰에서 로그인해도 같은 곡이 보인다.
 * 악보 파일은 폰마다 처음 열 때 서버 작업 번호([Work.jobId])로 받는다 ([ScoreStore.download]).
 *
 * - 저장·이름 바꾸기·삭제는 폰 목록을 먼저 바꾸고, 서버에는 뒤에서 보낸다.
 *   서버에 닿지 않으면 기억해 두었다가 다음 동기화 때 다시 보낸다.
 * - 이 업데이트 전에 폰에만 있던 곡도 처음 동기화할 때 서버에 올린다.
 * - 서버에 있다고 확인한 곡이 서버 목록에서 빠졌으면 다른 폰에서 지운 것이라 이 폰에서도 뺀다.
 */
object LibrarySync {
    private const val PREF = "rocky_library_sync"
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutex = Mutex()

    /** 서버에 연결하는 방법. 테스트에서 바꾼다. 로그인하지 않았거나 서버를 쓰지 않으면 null. */
    var apiFactory: (Context) -> MemberApi? = { ctx ->
        AuthRepository.token(ctx)?.takeIf { !Backend.local }?.let { MemberApi.from(ctx.applicationContext, it) }
    }

    /** 다른 기기 로그인으로 이 폰의 로그인이 끝났을 때 (서버가 401 "login required"). */
    var onLoggedOut: (() -> Unit)? = null

    fun changed(ctx: Context, workId: Long) {
        val uid = AuthRepository.currentUserId(ctx) ?: return
        edit(ctx, uid) { dirty += workId; removed -= workId }
        syncSoon(ctx)
    }

    fun removed(ctx: Context, workId: Long) {
        val uid = AuthRepository.currentUserId(ctx) ?: return
        edit(ctx, uid) { dirty -= workId; removed += workId }
        syncSoon(ctx)
    }

    fun syncSoon(ctx: Context) {
        val app = ctx.applicationContext
        scope.launch { runCatching { sync(app) } }
    }

    /**
     * 보낼 것을 보내고 서버 목록을 받아 폰 보관함을 바꾼다. 바뀌었으면 true.
     * 서버에 닿지 않으면 IOException (폰 목록은 그대로).
     */
    suspend fun sync(ctx: Context): Boolean {
        val uid = AuthRepository.currentUserId(ctx) ?: return false
        val api = apiFactory(ctx) ?: return false
        return withContext(Dispatchers.IO) {
            mutex.withLock {
                try {
                    syncLocked(ctx, uid, api)
                } catch (e: MemberApiException) {
                    if (e.code == 401 && e.message == "login required") onLoggedOut?.invoke()
                    throw e
                }
            }
        }
    }

    private fun syncLocked(ctx: Context, uid: Long, api: MemberApi): Boolean {
        val before = WorkStore.load(ctx, uid)
        // 예전 곡은 작업 번호를 받아 둔 결과(result.json)에서 찾는다.
        val local = before.map { w -> if (w.jobId != null) w else w.copy(jobId = ScoreStore.load(ctx, w.id)?.result?.id) }
        // 서버에 있다고 확인한 적 없는 곡은 올린다 (이 업데이트 전에 폰에만 저장한 곡).
        edit(ctx, uid) { for (w in local) if (w.jobId != null && w.id !in known && w.id !in removed) dirty += w.id }
        val state = read(ctx, uid)

        for (id in state.removed) {
            try {
                api.call("DELETE", "/me/works/$id")
            } catch (e: MemberApiException) {
                if (e.code !in 400..499 || e.code == 401) throw e
            }
            edit(ctx, uid) { removed -= id; known -= id }
        }
        for (id in state.dirty) {
            val w = local.firstOrNull { it.id == id }
            if (w?.jobId != null) {
                try {
                    api.call("PUT", "/me/works/$id", toJson(w))
                    edit(ctx, uid) { known += id }
                } catch (e: MemberApiException) {
                    // 서버가 이 곡을 받지 않는다(지워진 작업 등): 다시 보내도 같으니 이 폰에만 남긴다.
                    if (e.code !in 400..499 || e.code == 401) throw e
                }
            }
            // 보내는 사이 이 폰에서 이름을 또 바꿨으면 다음 동기화 때 다시 보낸다.
            val now = WorkStore.load(ctx, uid).firstOrNull { it.id == id }
            if (now == null || now.title == w?.title) edit(ctx, uid) { dirty -= id }
        }

        val server = JSONArray(api.get("/me/works"))
        val remote = (0 until server.length()).map { fromJson(server.getJSONObject(it)) }
        val remoteIds = remote.map { it.id }.toSet()
        val byId = local.associateBy { it.id }
        val merged = remote.map { r -> byId[r.id]?.audio?.let { r.copy(audio = it) } ?: r } +
            // 서버에 올리지 못한 곡(작업 번호를 모르는 아주 예전 곡)은 이 폰에만 남긴다.
            local.filter { it.id !in remoteIds && it.jobId == null }
        // 다른 폰에서 지운 곡: 이 폰에 받아 둔 파일도 지운다.
        for (w in local) if (w.id !in remoteIds && w.jobId != null) ScoreStore.dir(ctx, w.id).deleteRecursively()
        edit(ctx, uid) { known.clear(); known += remoteIds }
        // 동기화하는 사이 로그아웃했거나 다른 회원으로 바뀌었으면 쓰지 않는다.
        if (AuthRepository.currentUserId(ctx) != uid) return false
        // 그사이 이 폰에서 새로 저장·삭제한 곡이 있으면 다음 동기화에서 맞춘다.
        if (WorkStore.load(ctx, uid) != before) return false
        if (merged == before) return false
        WorkStore.save(ctx, uid, merged)
        return true
    }

    internal fun toJson(w: Work): JSONObject = JSONObject()
        .put("job_id", w.jobId).put("title", w.title).put("instruments", JSONArray(w.instruments))
        .put("date", w.date).put("original", JSONArray(w.original)).put("unrecognized", JSONArray(w.unrecognized))
        .put("personal", w.personal)

    internal fun fromJson(o: JSONObject) = Work(
        id = o.getLong("work_id"),
        title = o.getString("title"),
        instruments = MemberApi.strings(o.optJSONArray("instruments")),
        date = o.optString("date"),
        original = MemberApi.strings(o.optJSONArray("original")),
        unrecognized = MemberApi.strings(o.optJSONArray("unrecognized")),
        personal = o.optBoolean("personal"),
        jobId = o.optString("job_id").takeIf { it.isNotBlank() && !o.isNull("job_id") },
    )

    // ---------- 보낼 것 기록 (회원마다) ----------

    private class State(val dirty: MutableSet<Long>, val removed: MutableSet<Long>, val known: MutableSet<Long>)

    private val lock = Any()

    private fun read(ctx: Context, uid: Long): State = synchronized(lock) {
        val p = prefs(ctx)
        fun ids(k: String) = p.getString("${k}_$uid", "").orEmpty().split(",").mapNotNull { it.toLongOrNull() }.toMutableSet()
        State(ids("dirty"), ids("removed"), ids("known"))
    }

    private fun write(ctx: Context, uid: Long, s: State) = synchronized(lock) {
        prefs(ctx).edit().putString("dirty_$uid", s.dirty.joinToString(","))
            .putString("removed_$uid", s.removed.joinToString(","))
            .putString("known_$uid", s.known.joinToString(",")).commit()
    }

    private fun edit(ctx: Context, uid: Long, change: State.() -> Unit) = synchronized(lock) {
        val s = read(ctx, uid); s.change(); write(ctx, uid, s)
    }

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)

}
