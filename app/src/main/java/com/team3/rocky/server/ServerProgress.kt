// AI-generated with Claude Code, 2026-11-01
package com.team3.rocky.server

import com.team3.rocky.progress.JobProgress
import com.team3.rocky.progress.ProgressSource
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withContext
import java.io.IOException

/**
 * 서버에서 작업이 실패했을 때. message는 서버가 알려준 실패 이유.
 * reason이 있으면 서버 오류가 아니라 입력 거부(밴드 곡이 아님 등)이고, message는 사용자용 안내다.
 */
class JobFailedException(message: String, val reason: String? = null) : Exception(message)
class JobCancelledException : Exception()

/**
 * 서버의 GET /jobs/{id}를 pollMs마다 불러 진행 상태를 보낸다.
 * 잠깐 연결이 끊겨도(지하철 등) maxMissed번까지는 기다렸다 다시 묻는다.
 */
class ServerProgress(
    private val server: ScoreServer,
    private val pollMs: Long = 2_000,
    private val maxMissed: Int = 15,
    private val io: CoroutineDispatcher = Dispatchers.IO,
    /** 상태를 받을 때마다 불린다 (대기 안내 표시용) */
    private val onStatus: (JobStatus) -> Unit = {},
) : ProgressSource {

    override fun track(jobId: String): Flow<JobProgress> = flow {
        var missed = 0
        while (true) {
            val status = try {
                withContext(io) { server.status(jobId) }.also { missed = 0 }
            } catch (e: ApiException) {
                throw e  // 서버가 답은 했지만 거절함(키 틀림, 작업 없음): 기다려도 안 바뀐다
            } catch (e: IOException) {
                if (++missed > maxMissed) throw e
                null
            }
            if (status != null) {
                onStatus(status)
                if (status.isCancelled) throw JobCancelledException()
                if (status.isFailed) throw JobFailedException(status.error ?: "알 수 없는 오류", status.reason)
                emit(status.toProgress())
                if (status.isDone) return@flow
            }
            delay(pollMs)
        }
    }
}
