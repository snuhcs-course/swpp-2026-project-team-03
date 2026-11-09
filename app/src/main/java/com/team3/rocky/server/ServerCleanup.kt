package com.team3.rocky.server

import android.content.Context
import com.team3.rocky.auth.AuthRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import java.io.IOException

/**
 * 사용자가 지운 악보의 파일을 폰과 서버에서 지운다 (NFR-07).
 * 서버에 연결되지 않으면 작업 번호를 기억해 두었다가 다음에 다시 지운다.
 * 밴드에 공유한 악보는 밴드원이 같은 파일을 열기 때문에 지우지 않는다.
 * 서버도 밴드에 공유된 작업은 지우지 않는다 (409, 여기서는 지운 것으로 본다).
 */
object ServerCleanup {
    private const val PREF = "rocky_server_cleanup"
    private const val KEY = "pending"
    var serverFactory: (Context) -> ScoreServer = { RockyApi.from(it) }
    /** 서버에 닿지 않으면 false: 폰 파일은 지우고, 서버 삭제는 나중에 다시 보낸다 (서버가 공유 여부를 다시 본다). */
    var isShared: (Context, Long) -> Boolean = { ctx, id ->
        val uid = AuthRepository.currentUserId(ctx)
        uid != null && runBlocking { Backend.bands(ctx).isShared(uid, id) }
    }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Any()

    /** 악보 하나를 지운다. [serverJobId]를 모르면 폰에 받아 둔 결과(result.json)에서 찾는다. */
    fun deleteWork(ctx: Context, workId: Long, serverJobId: String? = null) {
        val app = ctx.applicationContext
        scope.launch { deleteNow(app, workId, serverJobId) }
    }

    /** [deleteWork]의 본문. 테스트에서 바로 부를 수 있게 따로 둔다. 서버에서 지웠으면 true. */
    fun deleteNow(app: Context, workId: Long, serverJobId: String? = null): Boolean {
        if (isShared(app, workId)) return false
        val id = serverJobId ?: ScoreStore.load(app, workId)?.result?.id
        ScoreStore.dir(app, workId).deleteRecursively()
        if (id == null) return false
        remember(app, id)
        return retryNow(app).contains(id)
    }

    /** 지우지 못하고 남은 서버 작업을 다시 지운다. */
    fun retryPending(ctx: Context) {
        val app = ctx.applicationContext
        if (pending(app).isNotEmpty()) scope.launch { retryNow(app) }
    }

    /** 남은 작업을 지우고, 이번에 지운 작업 번호를 돌려준다. */
    fun retryNow(app: Context): Set<String> {
        val server = runCatching { serverFactory(app) }.getOrNull() ?: return emptySet()
        val done = mutableSetOf<String>()
        for (id in pending(app)) {
            try {
                server.delete(id)
                done += id
            } catch (e: ApiException) {
                if (e.code in 400..499) done += id  // 서버가 받지 않는 요청은 다시 보내도 같다
            } catch (_: IOException) {
                // 서버에 연결되지 않음: 다음에 다시 시도
            }
        }
        synchronized(lock) { save(app, pending(app) - done) }
        return done
    }

    fun pending(ctx: Context): Set<String> = synchronized(lock) {
        prefs(ctx).getString(KEY, "").orEmpty().split(",").filter { it.isNotBlank() }.toSet()
    }

    private fun remember(ctx: Context, id: String) = synchronized(lock) { save(ctx, pending(ctx) + id) }

    private fun save(ctx: Context, ids: Set<String>) {
        prefs(ctx).edit().putString(KEY, ids.joinToString(",")).commit()
    }

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
}
