package com.team3.rocky.progress

import android.content.Context
import android.net.Uri
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.team3.rocky.Demo
import com.team3.rocky.Lang
import com.team3.rocky.AppSettings
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
    /** 개인 연습용 (내가 연주할 악기만). false면 밴드 합주용. */
    val personal: Boolean = false,
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
    /**
     * 실패했을 때 이 곡 그대로 '다시 시도'할 수 있는지. false면 목록에서 빠지고 '새로 만들기'(밴드 구성·곡 올리기부터)만 남는다.
     */
    var retryable by mutableStateOf(false)
        internal set
    /** '다시 시도'를 누를 수 있게 되는 시각 (System.currentTimeMillis). 서버가 기다리라고 하면(PDF 준비 실패 60초) 그만큼 뒤. */
    var retryAt by mutableStateOf(0L)
        internal set
    /** 서버에서 처리하다 실패했는지. 그러면 다시 시도할 때 POST /jobs/{id}/retry로 같은 곡을 다시 돌린다. */
    internal var serverFailed = false
    @Volatile internal var cancelRequested = false
    /**
     * 원곡 구성으로 보낸 것. 보통은 비어 있고(모델이 판단), '기타 대수 바꿔서 다시 만들기'일 때만
     * 모델이 찾은 원곡 악기 + 사용자가 고른 기타 대수가 들어 있다. ⚠️ 판단에 쓴다.
     */
    val claimed: List<String> = original
    /** 원곡에 있다고 보냈지만 원곡에서 소리가 거의 들리지 않은 파트 (⚠️) */
    var unrecognized by mutableStateOf<List<String>>(emptyList())
        internal set
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
        personal = personal,
        audio = audio.uri.toString(),
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

    /**
     * 방금 실패한 곡. 앱 안에서 팝업으로 한 번 알리고, 닫으면 null로 돌린다.
     * 다시 시도할 수 없는 곡은 이미 목록에서 빠졌고, 팝업에서 '새로 만들기'를 누를 수 있다.
     */
    var stopped by mutableStateOf<ScoreJob?>(null)

    val runningCount get() = jobs.count { !it.done && !it.failed }

    fun start(
        ctx: Context, title: String, lineup: List<String>, original: List<String>, audio: AudioFile,
        personal: Boolean = false,
    ): ScoreJob {
        val job = ScoreJob(System.currentTimeMillis(), title, lineup, original, audio, personal)
        jobs.add(0, job)
        launch(ctx.applicationContext, job)
        return job
    }

    /**
     * 실패한 작업을 이 곡 그대로 다시 시도한다 ([ScoreJob.retryable]일 때만).
     * - 서버에서 처리하다 실패했으면 같은 작업 번호로 다시 돌린다 (POST /jobs/{id}/retry, 음원을 다시 올리지 않음).
     *   서버가 끝난 단계는 건너뛰고 멈춘 단계부터 (채보가 끝났으면 PDF만) 다시 한다.
     * - 인터넷이 끊겨서 실패했으면 서버에서 돌던 작업에 다시 붙고, 아직 올리지 못했으면 다시 올린다.
     */
    fun retry(ctx: Context, job: ScoreJob, now: Long = System.currentTimeMillis()) {
        if (!job.retryable || now < job.retryAt) return
        job.runner?.cancel()
        val onServer = job.serverFailed && job.serverId != null
        job.error = null
        job.rejected = false
        job.serverFailed = false
        if (stopped === job) stopped = null
        JobNotifier.clear(ctx.applicationContext, job)
        // 아직 서버에 올라가지 않은 곡이면 진행 막대도 0%부터 다시 시작한다.
        if (job.serverId == null) { job.progress = null; job.bar.reset() }
        launch(ctx.applicationContext, job, retryOnServer = onServer)
    }

    private fun launch(app: Context, job: ScoreJob, retryOnServer: Boolean = false) {
        if (job !in jobs) return
        job.runner = scope.launch {
            try {
                if (retryOnServer) {
                    job.phase = tr("다시 시도하는 중", "Retrying")
                    withContext(Dispatchers.IO) { serverFactory(app).retry(job.serverId!!) }
                }
                runOnServer(app, job, job.audio)
                // 그사이 사용자가 지운 곡이면 알리지 않는다. 앱을 안 보고 있으면 휴대폰 알림으로.
                if (job in jobs) {
                    if (appVisible) Toast.makeText(
                        app, tr("'${job.title}' 악보가 완성됐어요", "'${job.title}' is ready"), Toast.LENGTH_LONG,
                    ).show() else JobNotifier.ready(app, job)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: JobCancelledException) {
                jobs.remove(job)
            } catch (e: Exception) {
                job.phase = null
                val f = classify(e)
                job.rejected = e is JobFailedException && e.reason != null
                job.serverFailed = e is JobFailedException
                job.retryable = f.retry
                job.retryAt = System.currentTimeMillis() + (f.waitSec ?: 0) * 1000L
                job.error = f.message
                if (!f.retry) {
                    // 이 곡 그대로는 다시 할 수 없다: 목록에서 빼고, 서버에 남은 실패 기록도 지운다.
                    // 팝업의 '새로 만들기'로 밴드 구성·곡 올리기부터 다시 한다.
                    jobs.remove(job)
                    job.serverId?.let { ServerCleanup.deleteWork(app, job.id, it) }
                }
                // 실패를 알린다: 앱 안에서는 팝업, 앱을 안 보고 있으면 휴대폰 알림도.
                stopped = job
                if (!appVisible) JobNotifier.stopped(app, job, f.message)
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
            // 서버의 note는 개발 용어일 수 있어서 그대로 보여주지 않고, 사용자가 알 것만 바꿔 적는다.
            job.phase = when {
                st.state == "queued" && (st.queuePosition ?: 0) > 1 ->
                    tr("대기 중 · 앞에 ${st.queuePosition!! - 1}곡", "Waiting · ${st.queuePosition!! - 1} ahead")
                st.state == "queued" -> tr("곧 시작해요", "Starting soon")
                else -> noteText(st.note)
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
            // 실패한 곡도 서버에 남은 기록·음원을 지운다 (다시 시도 직후 지워도 항상 지워진다: 서버 #25).
            if ((job.done && !job.saved) || (job.failed && job.serverId != null)) ServerCleanup.deleteWork(ctx, job.id, job.serverId)
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

    /**
     * 서버가 진행 중에 보내는 짧은 안내(note, 한국어 개발용 문장)를 사용자 문장으로.
     * 모르는 안내는 보여주지 않는다 (단계 이름이 대신 보인다).
     */
    fun noteText(note: String?): String? {
        if (note.isNullOrBlank()) return null
        val count = Regex("""\((\d+)/(\d+)\)""").find(note)?.value
        return when {
            "PDF" in note && "다시" in note ->
                tr("PDF를 다시 만드는 중", "Making the PDF again") + (count?.let { " $it" } ?: "")
            "GPU" in note -> tr("앞의 곡이 끝나길 기다리는 중", "Waiting for the song before yours")
            "agent" in note -> tr("곧 시작해요 · 준비하는 중", "Starting soon · getting ready")
            else -> null
        }
    }

    /** 실패를 어떻게 보여줄지: 안내 문장, 이 곡 그대로 다시 시도할 수 있는지, 기다릴 시간(초). */
    data class Failure(val message: String, val retry: Boolean, val waitSec: Int? = null)

    /**
     * 실패 이유를 나눈다 (조수빈 'ROCKY 곡 처리 결과별 동작', 서버 #25).
     * - 다시 시도할 수 있음: 서버가 retryable로 알려 준 실패(PDF 준비 실패·시간 초과·처리 오류), 인터넷 끊김
     * - 새로 만들어야 함: 입력 거부(짧음·무음·밴드 곡 아님), 작업 컴퓨터 없음, 업로드 중 서버 재시작,
     *   올린 음원이 서버에 없음(410), 파일 크기·형식·구성 거절(413·415·422), 파일을 못 엶, 옛 서버의 실패
     */
    fun classify(e: Exception): Failure = when (e) {
        is FileGoneException -> Failure(failureMessage(e), retry = false)
        is JobFailedException -> when {
            e.reason != null -> Failure(rejectionMessage(e.reason), retry = false)
            e.retryable == true -> Failure(serverFailureMessage(e.errorCode, e.retryFrom, e.userMessage, e.retryAfterSec), true, e.retryAfterSec)
            else -> Failure(serverFailureMessage(e.errorCode, e.retryFrom, e.userMessage, null), retry = false)
        }
        is ApiException -> when (e.code) {
            401 -> Failure(failureMessage(e), retry = true)  // 연결 설정을 고친 뒤 다시
            404, 410, 413, 415, 422 -> Failure(failureMessage(e), retry = false)
            else -> Failure(failureMessage(e), retry = true)
        }
        else -> Failure(failureMessage(e), retry = true)  // 인터넷 끊김 등
    }

    /** 서버 처리 실패(#25 error_code)를 사용자 문장으로. 무엇이 일어났고, 다시 시도하면 무엇을 하는지. */
    fun serverFailureMessage(code: String?, retryFrom: String?, serverMessage: String?, waitSec: Int?): String {
        // 사용자 말로: 무엇이 안 됐는지 + 다시 시도하면 무엇을 하는지. (채보·단계·프로그램 같은 말은 쓰지 않는다)
        val redo = if (retryFrom == "pdf") tr(
            "다시 시도하면 PDF만 다시 만들어요 (1~2분).",
            "Retry makes just the PDF again (1–2 min).",
        ) else tr(
            "다시 시도하면 멈춘 곳부터 이어서 만들어요 (10분 안팎).",
            "Retry picks up where it stopped (about 10 min).",
        )
        return when (code) {
            "pdf_network" -> {
                val wait = if ((waitSec ?: 60) >= 60 && (waitSec ?: 60) % 60 == 0) tr("${(waitSec ?: 60) / 60}분", "${(waitSec ?: 60) / 60} min")
                else tr("${waitSec}초", "$waitSec s")
                tr(
                    "악보를 PDF로 만드는 중에 오류가 났어요. $wait 뒤에 다시 시도하면 PDF만 다시 만들어요 (1~2분).",
                    "Something went wrong while making the PDF. Retry in $wait to make just the PDF again (1–2 min).",
                )
            }
            "timeout" -> tr("악보를 만드는 데 너무 오래 걸렸어요. ", "Making the scores took too long. ") + redo
            "pipeline_error" -> (if (retryFrom == "pdf") tr("악보를 PDF로 만드는 중에 오류가 났어요. ", "Something went wrong while making the PDF. ")
                else tr("악보를 만드는 중에 오류가 났어요. ", "Something went wrong while making the scores. ")) + redo +
                tr(" 두 번 연속 안 되면 팀에게 알려 주세요.", " If it fails twice, please tell the team.")
            "no_agent" -> tr(
                "지금은 악보를 만들 수 없는 상태예요. 잠시 뒤 새로 만들어 보고, 계속 안 되면 팀에게 알려 주세요.",
                "Scores can't be made right now. Try again later, and tell the team if it keeps happening.",
            )
            "upload_interrupted" -> tr(
                "곡을 보내는 중에 연결이 끊겼어요. 곡을 다시 올려 주세요.",
                "The connection dropped while sending the song. Please upload it again.",
            )
            // 앱이 모르는 새 종류: 서버 안내(한국어)가 있으면 그대로, 없으면 일반 문장.
            else -> serverMessage?.takeIf { AppSettings.lang == Lang.KO } ?: tr(
                "악보를 만들지 못했어요. 곡을 다시 올려 주세요.",
                "Couldn't make the scores. Please upload the song again.",
            )
        }
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
        "too_short" -> tr("곡이 너무 짧아서 악보를 만들 수 없어요. 30초 넘는 곡을 올려 주세요.", "The song is too short. Please upload one longer than 30 seconds.")
        "silent" -> tr("소리가 거의 없는 파일이에요. 다른 파일을 올려 주세요.", "The file is almost silent. Please pick another one.")
        else -> tr(
            "밴드 악기 소리가 거의 들리지 않아요. 밴드 곡을 올려 주세요.",
            "Hardly any band instruments. Please upload a band song.",
        )
    }

    fun failureMessage(e: Exception): String = when (e) {
        is FileGoneException -> tr(
            "곡 파일을 열 수 없어요. 새로 만들기에서 곡을 다시 골라 주세요.",
            "Can't open the file. Pick it again in a new score.",
        )
        // 입력 거부(밴드 곡이 아님 등): 다시 시도해도 같은 결과라 이유만 알려 준다.
        is JobFailedException -> if (e.reason != null) rejectionMessage(e.reason)
            else serverFailureMessage(e.errorCode, e.retryFrom, e.userMessage, e.retryAfterSec)
        is ApiException -> when (e.code) {
            401 -> tr("접속할 수 없어요. 연결 설정을 확인해 주세요.", "Can't connect. Check the connection settings.")
            413 -> tr("파일이 너무 커요. 더 짧은 곡이나 MP3 파일로 올려 주세요.", "The file is too big. Try a shorter song or an MP3.")
            415 -> tr("MP3나 WAV 파일만 올릴 수 있어요.", "Only MP3 or WAV files can be used.")
            422 -> tr(
                "원곡에 기타가 없으면 우리 밴드 기타는 1대까지만 만들 수 있어요.",
                "With no guitar in the song, we can make only one guitar part.",
            )
            404 -> tr("만들던 곡을 찾을 수 없어요. 곡을 다시 올려 주세요.", "Couldn't find this song. Please upload it again.")
            410 -> tr("이어서 만들 곡 파일이 없어요. 곡을 다시 올려 주세요.", "The song file is gone. Please upload it again.")
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
