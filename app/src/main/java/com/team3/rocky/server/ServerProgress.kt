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
 * 서버에서 작업이 실패했을 때. message는 서버의 개발자용 실패 이유 (사용자에게 보여주지 않는다).
 * reason이 있으면 서버 오류가 아니라 입력 거부(밴드 곡이 아님 등)다.
 * 나머지는 #25의 실패 정보: 종류, 사용자용 안내, 같은 곡으로 다시 시도할 수 있는지, 기다릴 시간, 어디부터 다시 하는지.
 */
class JobFailedException(
    message: String,
    val reason: String? = null,
    val errorCode: String? = null,
    val userMessage: String? = null,
    val retryable: Boolean? = null,
    val retryAfterSec: Int? = null,
    val retryFrom: String? = null,
) : Exception(message) {
    companion object {
        fun of(s: JobStatus) = JobFailedException(
            s.error ?: "알 수 없는 오류", s.reason, s.errorCode, s.message, s.retryable, s.retryAfterSec, s.retryFrom,
        )
    }
}
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
    /** 응답을 못 받을 때마다 연속으로 놓친 횟수와 함께 불린다 (다시 연결하는 중 안내용) */
    private val onMissed: (Int) -> Unit = {},
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
                onMissed(missed)
                null
            }
            if (status != null) {
                onStatus(status)
                if (status.isCancelled) throw JobCancelledException()
                if (status.isFailed) throw JobFailedException.of(status)
                emit(status.toProgress())
                if (status.isDone) return@flow
            }
            delay(pollMs)
        }
    }
}
