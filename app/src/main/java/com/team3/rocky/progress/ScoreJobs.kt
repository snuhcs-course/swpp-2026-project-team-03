package com.team3.rocky.progress

import android.content.Context
import android.net.Uri
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.team3.rocky.Demo
import com.team3.rocky.Work
import com.team3.rocky.server.ApiException
import com.team3.rocky.server.JobFailedException
import com.team3.rocky.server.JobCancelledException
import com.team3.rocky.server.RockyApi
import com.team3.rocky.server.ScoreServer
import com.team3.rocky.server.ScoreStore
import com.team3.rocky.server.ServerCleanup
import com.team3.rocky.server.ServerProgress
import com.team3.rocky.server.ServerSettings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** 사용자가 고른 음원 파일. 데모 곡이면 없음(null). */
data class AudioFile(val uri: Uri, val fileName: String)

/** 백그라운드에서 만들고 있는 악보 한 곡. */
class ScoreJob(
    val id: Long,
    val title: String,
    val lineup: List<String>,
    original: List<String>,
    /** null이면 데모 곡: 서버 없이 미리 준비한 결과를 보여준다. */
    val audio: AudioFile? = null,
) {
    var progress by mutableStateOf<JobProgress?>(null)
        internal set
    /** 결과 화면에서 보관함에 저장했는지 */
    var saved by mutableStateOf(false)
    /** 실패했을 때 사용자에게 보여줄 이유. null이면 실패 아님 */
    var error by mutableStateOf<String?>(null)
        internal set
    /** 서버 결과를 받은 뒤에는 서버가 판단한 원곡 구성으로 바뀐다 (AI 생성 표시가 정확해진다). */
    var original by mutableStateOf(original)
        internal set
    /** 업로드 중 같은 진행률이 없는 단계 안내 */
    var phase by mutableStateOf<String?>(null)
        internal set
    var cancelling by mutableStateOf(false)
        internal set
    var cancelError by mutableStateOf<String?>(null)
        internal set
    @Volatile internal var cancelRequested = false
    /** 서버 작업 번호. 업로드가 끝나면 생긴다 */
    @Volatile internal var serverId: String? = null
    internal var runner: Job? = null

    val done get() = progress?.done == true
    val failed get() = error != null
    val isServer get() = audio != null

    /** 완성되면 결과 화면에서 쓰는 작업 정보 (id가 같아서 저장 여부·서버 결과 파일을 맞출 수 있다). */
    fun toWork() = Work(
        id = id, title = title, instruments = lineup,
        date = SimpleDateFormat("yyyy.MM.dd HH:mm", Locale.KOREA).format(Date(id)),
        original = original,
    )
}

/**
 * 악보 만들기 작업 목록. 화면을 옮겨 다녀도 계속 돌아가도록 화면 밖(앱 전체)에서 관리한다.
 * 음원을 고른 곡은 ROCKY 서버에서 만들고(업로드 → 진행 상태 → 결과 받기),
 * 데모 곡은 [DemoProgress]로 흉내 낸다. 앱을 완전히 끄면 목록은 사라진다.
 */
object ScoreJobs {
    val jobs = mutableStateListOf<ScoreJob>()
    var demoSource: ProgressSource = DemoProgress
    /** 테스트에서 가짜 서버로 바꿀 수 있게 */
    var serverFactory: (Context) -> ScoreServer = { RockyApi.from(it) }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    val runningCount get() = jobs.count { !it.done && !it.failed }

    fun start(
        ctx: Context, title: String, lineup: List<String>, original: List<String>, audio: AudioFile? = null,
    ): ScoreJob {
        val job = ScoreJob(System.currentTimeMillis(), title, lineup, original, audio)
        jobs.add(0, job)
        launch(ctx.applicationContext, job)
        return job
    }

    /** 실패한 작업을 다시 시도한다. 업로드까지 끝났으면 서버 작업을 이어서 본다. */
    fun retry(ctx: Context, job: ScoreJob) {
        job.runner?.cancel()
        job.error = null
        launch(ctx.applicationContext, job)
    }

    /** 서버로 만들지 못한 곡을 데모 결과로 바꿔 보여준다 (시연에서 서버가 안 될 때). */
    fun useDemo(ctx: Context, job: ScoreJob): ScoreJob {
        remove(job)
        return start(ctx, job.title, job.lineup, Demo.DEMO_ORIGINAL)
    }

    private fun launch(app: Context, job: ScoreJob) {
        if (job !in jobs) return
        job.runner = scope.launch {
            try {
                if (job.audio == null) {
                    demoSource.track(job.id.toString()).collect { job.progress = it }
                } else {
                    runOnServer(app, job, job.audio)
                }
                if (job in jobs)
                    Toast.makeText(app, "'${job.title}' 악보가 완성됐어요. 진행상황 탭에서 볼 수 있어요", Toast.LENGTH_LONG).show()
            } catch (e: CancellationException) {
                throw e
            } catch (e: JobCancelledException) {
                jobs.remove(job)
            } catch (e: Exception) {
                job.phase = null
                job.error = failureMessage(e)
            }
        }
    }

    private suspend fun runOnServer(app: Context, job: ScoreJob, audio: AudioFile) {
        val server = serverFactory(app)
        if (job.serverId == null) {
            if (!ServerSettings.isConfigured(app)) throw IOException("서버 주소가 설정되지 않았어요")
            job.phase = "음원을 서버에 올리는 중"
            job.serverId = withContext(Dispatchers.IO) {
                val input = app.contentResolver.openInputStream(audio.uri)
                    ?: throw IOException("음원 파일을 열 수 없어요")
                input.use {
                    // lineup·original은 앱 이름 그대로(guitar2 = 기타 2대) 보내고,
                    // 서버가 unified.py 형식(keyboard,bass,guitar1|guitar2,drums / unknown)으로 바꾼다.
                    server.upload(it, audio.fileName, job.title, requestedParts(job.lineup),
                        original = job.original, lineup = job.lineup).also { id -> job.serverId = id }
                }
            }
        }
        // An upload already in progress may finish after the user pressed cancel.
        // Keep its runner here until cancel() has sent the new server ID upstream.
        while (job.cancelRequested) delay(100)
        job.phase = null
        val id = job.serverId!!
        val tracker = ServerProgress(server, onStatus = { st ->
            job.phase = st.note ?: when {
                st.state == "queued" && (st.queuePosition ?: 0) > 1 -> "앞의 곡을 기다리는 중 (${st.queuePosition}번째)"
                st.state == "queued" -> "곧 시작해요"
                else -> null
            }
        })
        tracker.track(id).collect { p ->
            // 마지막 '완료'는 결과 파일을 다 받은 뒤에 보낸다.
            job.progress = if (p.done) p.copy(done = false, etaSec = 0) else p
        }
        job.phase = "완성된 악보를 받는 중"
        val local = withContext(Dispatchers.IO) { ScoreStore.download(app, server, id, job.id) }
        job.original = originalFromServer(job.lineup, local.result.originalParts, local.result.generatedParts)
        job.phase = null
        job.progress = JobProgress(Stage.ARRANGE, 1, 1, 0, done = true)
    }

    fun find(id: Long) = jobs.firstOrNull { it.id == id }

    /** Stop the server job first, then remove the card once the Pod is gone. */
    fun cancel(ctx: Context, job: ScoreJob) {
        if (job.done || job.failed) {
            remove(job)
            // 보관함에 저장하지 않은 결과는 다시 열 수 없으니 폰과 서버의 파일도 지운다 (NFR-07).
            if (job.isServer && job.done && !job.saved) ServerCleanup.deleteWork(ctx, job.id, job.serverId)
            return
        }
        if (job.cancelling) return
        job.cancelling = true
        job.cancelRequested = true
        job.cancelError = null
        job.phase = "취소 중"
        if (!job.isServer) {
            job.runner?.cancel()
            jobs.remove(job)
            return
        }
        val app = ctx.applicationContext
        scope.launch {
            try {
                while (job.serverId == null && job.runner?.isActive == true) delay(100)
                val id = job.serverId
                if (id == null) {
                    job.runner?.cancel()
                    jobs.remove(job)
                    return@launch
                }
                val server = serverFactory(app)
                val state = withContext(Dispatchers.IO) { server.cancel(id) }
                if (state == "complete") {
                    job.cancelRequested = false
                    job.cancelling = false
                    job.phase = null
                    if (job.runner?.isActive != true) launch(app, job)
                    return@launch
                }
                if (state == "failed") {
                    job.cancelRequested = false
                    job.cancelling = false
                    job.phase = null
                    return@launch
                }
                job.runner?.cancel()
                if (state == "cancelled") {
                    jobs.remove(job)
                    return@launch
                }
                val stopped = withTimeoutOrNull(120_000) {
                    while (true) {
                        val status = withContext(Dispatchers.IO) { server.status(id) }
                        if (status.isCancelled || status.isDone || status.isFailed)
                            return@withTimeoutOrNull status.state
                        delay(500)
                    }
                    @Suppress("UNREACHABLE_CODE")
                    "running"
                }
                when (stopped) {
                    "cancelled" -> jobs.remove(job)
                    "complete", "failed" -> {
                        job.cancelRequested = false
                        job.cancelling = false
                        job.phase = null
                        launch(app, job) // completion or failure won the race
                    }
                    else -> {
                        job.cancelRequested = false
                        job.cancelling = false
                        job.cancelError = "서버의 취소 완료를 확인하지 못했어요. 다시 눌러 확인해 주세요."
                        launch(app, job)
                    }
                }
            } catch (e: Exception) {
                job.cancelRequested = false
                job.cancelling = false
                job.phase = null
                job.cancelError = "취소 요청이 전달되지 않았어요. 다시 시도해 주세요. (${e.message})"
                if (job.runner?.isActive != true) launch(app, job)
            }
        }
    }

    /** 완성되거나 실패한 카드만 로컬 목록에서 지운다. 실행 중인 서버 작업은 cancel()을 쓴다. */
    fun remove(job: ScoreJob) {
        job.runner?.cancel()
        jobs.remove(job)
    }

    /** 로그아웃하면 다른 회원에게 보이지 않게 비운다. */
    fun clear(ctx: Context) {
        jobs.toList().forEach { if (!it.done && !it.failed) cancel(ctx, it) else it.runner?.cancel() }
        jobs.clear()
    }

    /** 앱의 파트 이름 → 서버(unified.py --requested)의 악기 이름. 기타 2대도 guitar 하나로 보낸다. */
    fun requestedParts(parts: List<String>): List<String> =
        parts.map { if (it == Demo.GUITAR2) "guitar" else it }
            .filter { it in Demo.INSTRUMENTS }
            .distinct()

    /**
     * 서버가 판단한 원곡 구성을 앱의 파트 이름으로.
     * 원곡에 기타가 있으면 기타 2도 원곡 파트로 본다. 단 서버가 기타를 새로 만들었으면
     * (generated_parts에 guitar, 원곡 기타 1대 → 우리 밴드 2대) 기타 2는 AI 생성 파트다.
     */
    fun originalFromServer(lineup: List<String>, serverOriginal: List<String>,
                           generated: List<String> = emptyList()): List<String> {
        val set = serverOriginal.filter { it in Demo.INSTRUMENTS }.toMutableSet()
        if ("guitar" in set && Demo.GUITAR2 in lineup && "guitar" !in generated) set += Demo.GUITAR2
        return Demo.ordered(set)
    }

    /** 실패 이유를 사용자가 알아들을 말로. */
    fun failureMessage(e: Exception): String = when (e) {
        // 입력 거부: 다시 시도해도 같은 결과라 서버 안내만 보여준다.
        is JobFailedException -> if (e.reason != null) e.message ?: "이 파일로는 악보를 만들 수 없어요."
            else "서버에서 처리하다 멈췄어요. (${e.message})"
        is ApiException -> when (e.code) {
            401 -> "서버 키가 맞지 않아요. 음원 업로드 화면 아래 '서버 설정'에서 확인해 주세요."
            413 -> "음원 파일이 너무 커요. 더 짧은 곡이나 MP3로 올려 주세요."
            415 -> "MP3, WAV, FLAC, M4A 음원만 올릴 수 있어요."
            422 -> "이 밴드 구성으로는 만들 수 없어요. 원곡에 기타가 없으면 기타는 1대까지만 새로 만들 수 있어요."
            404 -> "서버에서 작업을 찾을 수 없어요. 새로 만들어 주세요."
            else -> "서버가 요청을 처리하지 못했어요. (HTTP ${e.code})"
        }
        is IOException -> "서버에 연결할 수 없어요. 인터넷 연결이나 서버 주소를 확인해 주세요. (${e.message})"
        else -> "알 수 없는 오류가 났어요. (${e.message})"
    }
}
