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
import com.team3.rocky.tr
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

/** 사용자가 고른 음원 파일. */
data class AudioFile(val uri: Uri, val fileName: String)

/** 백그라운드에서 만들고 있는 악보 한 곡. */
class ScoreJob(
    val id: Long,
    val title: String,
    val lineup: List<String>,
    original: List<String>,
    val audio: AudioFile,
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
    /** 서버가 입력을 거부했는지 (밴드 곡이 아님 등). 다시 시도해도 같은 결과라 '다시 시도'를 보여주지 않는다. */
    var rejected by mutableStateOf(false)
        internal set
    @Volatile internal var cancelRequested = false
    /** 사용자가 고른 원곡 구성 그대로 (비어 있으면 '잘 모르겠어요'). ⚠️ 판단에 쓴다. */
    val claimed: List<String> = original
    /** 원곡에 있다고 골랐지만 원곡에서 소리가 거의 들리지 않은 파트 (⚠️) */
    var unrecognized by mutableStateOf<List<String>>(emptyList())
        internal set
    /** 원곡에 없다고 했지만(고르지 않았지만) 원곡에서 소리가 뚜렷했던 파트 */
    var overlooked by mutableStateOf<List<String>>(emptyList())
        internal set
    /** 원곡 악기를 실제와 다르게 고른 것 같은지. 그러면 '악기 다시 선택'을 권한다. */
    val instrumentDoubt get() = unrecognized.isNotEmpty() || overlooked.isNotEmpty()
    /** 서버 작업 번호. 업로드가 끝나면 생긴다 */
    @Volatile internal var serverId: String? = null
    internal var runner: Job? = null
    /** 화면의 진행 막대. 서버 값이 뛰더라도 일정하게 올라가도록 따로 둔다 */
    val bar = SmoothProgress()

    val done get() = progress?.done == true
    val failed get() = error != null

    /** 완성되면 결과 화면에서 쓰는 작업 정보 (id가 같아서 저장 여부·서버 결과 파일을 맞출 수 있다). */
    fun toWork() = Work(
        id = id, title = title, instruments = lineup,
        date = SimpleDateFormat("yyyy.MM.dd HH:mm", Locale.KOREA).format(Date(id)),
        original = original,
        unrecognized = unrecognized,
    )
}

/**
 * 악보 만들기 작업 목록. 화면을 옮겨 다녀도 계속 돌아가도록 화면 밖(앱 전체)에서 관리한다.
 * 고른 곡을 ROCKY 서버에서 만든다(업로드 → 진행 상태 → 결과 받기). 앱을 완전히 끄면 목록은 사라진다.
 */
object ScoreJobs {
    val jobs = mutableStateListOf<ScoreJob>()
    /** 테스트에서 가짜 서버로 바꿀 수 있게 */
    var serverFactory: (Context) -> ScoreServer = { RockyApi.from(it) }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    /** 앱 화면이 보이는 중인지 (MainActivity가 알려 준다). 안 보일 때 멈추면 휴대폰 알림을 보낸다. */
    @Volatile var appVisible = false

    /** 방금 멈춘 곡. 앱 안에서 팝업으로 한 번 알리고, 닫으면 null로 돌린다. */
    var stopped by mutableStateOf<ScoreJob?>(null)

    val runningCount get() = jobs.count { !it.done && !it.failed }

    fun start(
        ctx: Context, title: String, lineup: List<String>, original: List<String>, audio: AudioFile,
    ): ScoreJob {
        val job = ScoreJob(System.currentTimeMillis(), title, lineup, original, audio)
        jobs.add(0, job)
        launch(ctx.applicationContext, job)
        return job
    }

    /**
     * 실패한 작업을 다시 시도한다.
     * 인터넷이 끊겨서 실패했으면 서버에서 돌던 작업에 다시 붙고,
     * 서버에서 처리하다 실패했으면(같은 실패가 반복되므로) 음원을 처음부터 다시 올린다.
     */
    fun retry(ctx: Context, job: ScoreJob) {
        job.runner?.cancel()
        job.error = null
        job.rejected = false
        if (stopped === job) stopped = null
        JobNotifier.clear(ctx.applicationContext, job)
        // 처음부터 다시 만들면 진행 막대도 0%부터 다시 시작한다.
        if (job.serverId == null) { job.progress = null; job.bar.reset() }
        launch(ctx.applicationContext, job)
    }

    private fun launch(app: Context, job: ScoreJob) {
        if (job !in jobs) return
        job.runner = scope.launch {
            try {
                runOnServer(app, job, job.audio)
                // 그사이 사용자가 지웠거나 '악기 다시 선택'으로 바꾼 곡이면 알리지 않는다.
                if (job in jobs) Toast.makeText(
                    app, tr("'${job.title}' 악보가 완성됐어요", "'${job.title}' is ready"), Toast.LENGTH_LONG,
                ).show()
            } catch (e: CancellationException) {
                throw e
            } catch (e: JobCancelledException) {
                jobs.remove(job)
            } catch (e: Exception) {
                job.phase = null
                // 서버에서 실패했거나 서버가 작업을 잃어버렸으면, 다시 시도할 때 새로 올린다.
                if (e is JobFailedException || (e is ApiException && e.code == 404)) job.serverId = null
                job.rejected = e is JobFailedException && e.reason != null
                val reason = failureMessage(e)
                job.error = reason
                // 멈춘 것을 알린다: 앱 안에서는 팝업, 앱을 안 보고 있으면 휴대폰 알림도.
                stopped = job
                if (!appVisible) JobNotifier.stopped(app, job, reason)
            }
        }
    }

    private suspend fun runOnServer(app: Context, job: ScoreJob, audio: AudioFile) {
        val server = serverFactory(app)
        if (job.serverId == null) {
            if (!ServerSettings.isConfigured(app)) throw IOException("no server address")
            job.phase = tr("곡을 보내는 중", "Sending your song")
            job.serverId = withContext(Dispatchers.IO) {
                val input = app.contentResolver.openInputStream(audio.uri)
                    ?: throw FileGoneException()
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
        // 서버에 올라간 순간부터 1%. (올리는 중에는 '곡을 보내는 중'으로 0%)
        job.bar.started()
        val id = job.serverId!!
        val tracker = ServerProgress(server, maxMissed = 90, onStatus = { st ->
            // 서버의 note는 영어·개발 용어일 수 있어서 보여주지 않고, 사용자가 알 것만 적는다.
            job.phase = when {
                st.state == "queued" && (st.queuePosition ?: 0) > 1 ->
                    tr("대기 중 · 앞에 ${st.queuePosition!! - 1}곡", "Waiting · ${st.queuePosition!! - 1} ahead")
                st.state == "queued" -> tr("곧 시작해요", "Starting soon")
                else -> null
            }
        }, onMissed = { missed ->
            // 잠깐 끊긴 것은 실패로 보지 않고 다시 연결되기를 기다린다.
            if (missed > 0) job.phase = tr("연결 끊김 · 다시 연결 중", "Disconnected · reconnecting")
        })
        tracker.track(id).collect { p ->
            // 마지막 '완료'는 결과 파일을 다 받은 뒤에 보낸다.
            job.progress = if (p.done) p.copy(done = false, etaSec = 0) else p
        }
        job.phase = tr("완성된 악보를 받는 중", "Downloading your scores")
        val local = withContext(Dispatchers.IO) { ScoreStore.download(app, server, id, job.id) }
        val faint = Demo.faintParts(job.lineup, job.claimed, local.result.faintParts)
            .filter { it !in local.result.generatedParts }
        job.unrecognized = faint
        job.overlooked = Demo.overlookedParts(job.lineup, job.claimed, local.result.undeclaredParts)
        // ⚠️ 파트는 AI가 만든 것이 아니라 원곡에서 옮긴 파트이므로 ✨ 대상에서 뺀다.
        job.original = Demo.ordered(
            originalFromServer(job.lineup, local.result.originalParts, local.result.generatedParts) + faint,
        )
        job.phase = null
        job.progress = JobProgress(Stage.ARRANGE, 1, 1, 0, done = true)
    }

    fun find(id: Long) = jobs.firstOrNull { it.id == id }

    /** Stop the server job first, then remove the card once the Pod is gone. */
    fun cancel(ctx: Context, job: ScoreJob) {
        if (job.done || job.failed) {
            remove(job)
            // 보관함에 저장하지 않은 결과는 다시 열 수 없으니 폰과 서버의 파일도 지운다 (NFR-07).
            if (job.done && !job.saved) ServerCleanup.deleteWork(ctx, job.id, job.serverId)
            return
        }
        if (job.cancelling) return
        job.cancelling = true
        job.cancelRequested = true
        job.cancelError = null
        job.phase = tr("취소 중", "Cancelling")
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
                        job.cancelError = tr(
                            "취소됐는지 확인하지 못했어요. 다시 눌러 주세요.",
                            "Couldn't confirm the cancel. Tap again.",
                        )
                        launch(app, job)
                    }
                }
            } catch (e: Exception) {
                job.cancelRequested = false
                job.cancelling = false
                job.phase = null
                job.cancelError = tr(
                    "취소하지 못했어요. 인터넷을 확인하고 다시 눌러 주세요.",
                    "Couldn't cancel. Check the internet and tap again.",
                )
                if (job.runner?.isActive != true) launch(app, job)
            }
        }
    }

    /** 완성되거나 실패한 카드만 로컬 목록에서 지운다. 실행 중인 서버 작업은 cancel()을 쓴다. */
    fun remove(job: ScoreJob) {
        job.runner?.cancel()
        jobs.remove(job)
        if (stopped === job) stopped = null
    }

    /** 로그아웃하면 다른 회원에게 보이지 않게 비운다. */
    fun clear(ctx: Context) {
        jobs.toList().forEach { if (!it.done && !it.failed) cancel(ctx, it) else it.runner?.cancel() }
        jobs.clear()
        stopped = null
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

    /** 실패 이유를 사용자가 알아들을 말로. 서버·HTTP 같은 말은 쓰지 않고, 무엇을 하면 되는지 적는다. */
    /** 서버가 입력을 거부한 이유(reason 코드)를 사용자 문장으로. 서버 안내는 한국어뿐이라 앱에서 바꾼다. */
    fun rejectionMessage(reason: String): String = when (reason) {
        "too_short" -> tr("곡이 너무 짧아서 악보를 만들 수 없어요.", "The song is too short to make scores.")
        "silent" -> tr("소리가 거의 들리지 않는 파일이에요.", "The file is almost silent.")
        else -> tr(
            "밴드 악기 소리가 거의 들리지 않아요. 밴드 곡을 올려 주세요.",
            "Hardly any band instruments. Please upload a band song.",
        )
    }

    fun failureMessage(e: Exception): String = when (e) {
        is FileGoneException -> tr(
            "곡 파일을 열 수 없어요. 다시 골라 주세요.",
            "Can't open the file. Pick it again.",
        )
        // 입력 거부(밴드 곡이 아님 등): 다시 시도해도 같은 결과라 이유만 알려 준다.
        is JobFailedException -> if (e.reason != null) rejectionMessage(e.reason)
            else tr("만들지 못했어요. 다시 시도하면 처음부터 만들어요.", "Failed. Retry to start over.")
        is ApiException -> when (e.code) {
            401 -> tr("접속할 수 없어요. 연결 설정을 확인해 주세요.", "Can't connect. Check the connection settings.")
            413 -> tr("파일이 너무 커요. 짧은 곡이나 MP3로 올려 주세요.", "File too big. Try a shorter song or MP3.")
            415 -> tr("MP3나 WAV 파일만 올릴 수 있어요.", "Only MP3 or WAV files can be used.")
            422 -> tr(
                "원곡에 기타가 없으면 기타는 1대까지만 만들 수 있어요.",
                "If the song has no guitar, we can add only one guitar.",
            )
            404 -> tr("곡을 찾을 수 없어요. 다시 시도하면 처음부터 만들어요.", "Song not found. Retry to start over.")
            // 오류 번호는 보여주지 않는다 (Nielsen 9: 쉬운 말로, 해결 방법과 함께).
            else -> tr("문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.", "Something went wrong. Retry in a moment.")
        }
        is IOException -> tr(
            "인터넷에 연결할 수 없어요. 확인 후 다시 시도해 주세요.",
            "No connection. Check and retry.",
        )
        else -> tr("문제가 생겼어요. 다시 시도해 주세요.", "Something went wrong. Retry.")
    }
}

/** 고른 음원 파일을 더 이상 열 수 없을 때 (파일이 지워졌거나 읽기 권한이 사라짐). */
class FileGoneException : IOException("audio file is gone")
