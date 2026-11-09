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
import com.team3.rocky.server.RockyApi
import com.team3.rocky.server.ScoreServer
import com.team3.rocky.server.ScoreStore
import com.team3.rocky.server.ServerProgress
import com.team3.rocky.server.ServerSettings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
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
    /** 사용자가 고른 원곡 구성 그대로 (비어 있으면 '잘 모르겠어요'). ⚠️ 판단에 쓴다. */
    val claimed: List<String> = original
    /** 원곡에 있다고 골랐지만 원곡에서 찾지 못한 파트 (⚠️) */
    var unrecognized by mutableStateOf<List<String>>(emptyList())
        internal set
    /** 서버 작업 번호. 업로드가 끝나면 생긴다 */
    internal var serverId: String? = null
    internal var runner: Job? = null
    /** 취소할 때 서버에도 알리려고 들고 있는다 */
    internal var server: ScoreServer? = null
    /** 화면의 진행 막대. 서버 값이 뛰더라도 일정하게 올라가도록 따로 둔다 */
    val bar = SmoothProgress()

    val done get() = progress?.done == true
    val failed get() = error != null
    val isServer get() = audio != null

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

    /**
     * 실패한 작업을 다시 시도한다.
     * 인터넷이 끊겨서 실패했으면 서버에서 돌던 작업에 다시 붙고,
     * 서버에서 처리하다 실패했으면(같은 실패가 반복되므로) 음원을 처음부터 다시 올린다.
     */
    fun retry(ctx: Context, job: ScoreJob) {
        job.runner?.cancel()
        job.error = null
        // 처음부터 다시 만들면 진행 막대도 0%부터 다시 시작한다.
        if (job.serverId == null) { job.progress = null; job.bar.reset() }
        launch(ctx.applicationContext, job)
    }

    /** 서버로 만들지 못한 곡을 데모 결과로 바꿔 보여준다 (시연에서 서버가 안 될 때). */
    fun useDemo(ctx: Context, job: ScoreJob): ScoreJob {
        remove(job)
        return start(ctx, job.title, job.lineup, Demo.DEMO_ORIGINAL)
    }

    private fun launch(app: Context, job: ScoreJob) {
        job.runner = scope.launch {
            try {
                if (job.audio == null) {
                    demoSource.track(job.id.toString()).collect { job.progress = it }
                    // 데모 곡의 실제 원곡 구성과 비교해 ⚠️를 정한다 (예: 피아노가 원곡에 있다고 고르면 ⚠️).
                    job.unrecognized = Demo.unrecognized(job.lineup, job.claimed, Demo.DEMO_ORIGINAL)
                } else {
                    runOnServer(app, job, job.audio)
                }
                Toast.makeText(
                    app, tr("'${job.title}' 악보가 완성됐어요", "'${job.title}' is ready"), Toast.LENGTH_LONG,
                ).show()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                job.phase = null
                // 서버에서 실패했거나 서버가 작업을 잃어버렸으면, 다시 시도할 때 새로 올린다.
                if (e is JobFailedException || (e is ApiException && e.code == 404)) job.serverId = null
                job.error = failureMessage(e)
            }
        }
    }

    private suspend fun runOnServer(app: Context, job: ScoreJob, audio: AudioFile) {
        val server = serverFactory(app)
        job.server = server
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
                        original = job.original, lineup = job.lineup)
                }
            }
        }
        job.phase = null
        val id = job.serverId!!
        val tracker = ServerProgress(server, maxMissed = 90, onStatus = { st ->
            // 서버의 note는 영어·개발 용어일 수 있어서 보여주지 않고, 사용자가 알 것만 적는다.
            job.phase = when {
                st.state == "queued" && (st.queuePosition ?: 0) > 1 ->
                    tr("앞에 ${st.queuePosition!! - 1}곡이 있어요. 차례를 기다리는 중", "${st.queuePosition!! - 1} song(s) ahead of yours")
                st.state == "queued" -> tr("곧 시작해요", "Starting soon")
                else -> null
            }
        }, onMissed = { missed ->
            // 잠깐 끊긴 것은 실패로 보지 않고 다시 연결되기를 기다린다.
            if (missed > 0) job.phase = tr("연결이 잠시 끊겼어요. 다시 연결하는 중", "Connection lost. Reconnecting")
        })
        tracker.track(id).collect { p ->
            // 마지막 '완료'는 결과 파일을 다 받은 뒤에 보낸다.
            job.progress = if (p.done) p.copy(done = false, etaSec = 0) else p
        }
        job.phase = tr("완성된 악보를 받는 중", "Downloading your scores")
        val local = withContext(Dispatchers.IO) { ScoreStore.download(app, server, id, job.id) }
        val missing = Demo.unrecognized(
            job.lineup, job.claimed, local.result.originalParts, reported = local.result.undetectedParts,
        ).filter { it !in local.result.generatedParts }
        job.unrecognized = missing
        // ⚠️ 파트는 AI가 만든 것이 아니라 원곡에서 옮기려던 파트이므로 ✨ 대상에서 뺀다.
        job.original = Demo.ordered(
            originalFromServer(
                job.lineup, local.result.originalParts,
                generated = local.result.generatedParts, resultParts = local.result.instruments.keys,
            ) + missing,
        )
        job.phase = null
        job.progress = JobProgress(Stage.ARRANGE, 1, 1, 0, done = true)
    }

    fun find(id: Long) = jobs.firstOrNull { it.id == id }

    /** 목록에서 지운다. 아직 만드는 중이면 취소하고, 서버에도 멈추라고 알린다(다음 곡이 기다리지 않게). */
    fun remove(job: ScoreJob) {
        job.runner?.cancel()
        jobs.remove(job)
        val id = job.serverId
        val server = job.server
        if (id != null && server != null && !job.done && !job.failed) {
            scope.launch(Dispatchers.IO) { runCatching { server.cancel(id) } }
        }
    }

    /** 로그아웃하면 다른 회원에게 보이지 않게 비운다. */
    fun clear() {
        jobs.forEach { it.runner?.cancel() }
        jobs.clear()
    }

    /** 앱의 파트 이름 → 서버(unified.py --requested)의 악기 이름. 기타 2대도 guitar 하나로 보낸다. */
    fun requestedParts(parts: List<String>): List<String> =
        parts.map { if (it == Demo.GUITAR2) "guitar" else it }
            .filter { it in Demo.INSTRUMENTS }
            .distinct()

    /**
     * 서버가 판단한 원곡 구성을 앱의 파트 이름으로. 원곡에 기타가 있으면 기타 2도 원곡 파트로 본다.
     * 단, 원곡 기타가 1대라서 AI가 두 번째 기타를 만든 곡(결과에 guitar_2가 따로 오거나
     * generated_parts에 들어 있음)은 기타 2를 원곡에서 빼서 ✨ AI 생성으로 보이게 한다.
     */
    fun originalFromServer(
        lineup: List<String>,
        serverOriginal: List<String>,
        generated: List<String> = emptyList(),
        resultParts: Collection<String> = emptyList(),
    ): List<String> {
        val set = serverOriginal.filter { it in Demo.INSTRUMENTS }.toMutableSet()
        val secondGuitarMade = "guitar_2" in resultParts || generated.any { it == "guitar_2" || it == Demo.GUITAR2 }
        if ("guitar" in set && Demo.GUITAR2 in lineup && !secondGuitarMade) set += Demo.GUITAR2
        set -= generated.filter { it in Demo.INSTRUMENTS }.toSet()
        return Demo.ordered(set)
    }

    /** 실패 이유를 사용자가 알아들을 말로. 서버·HTTP 같은 말은 쓰지 않고, 무엇을 하면 되는지 적는다. */
    fun failureMessage(e: Exception): String = when (e) {
        is FileGoneException -> tr(
            "고른 곡 파일을 열 수 없어요. 곡을 다시 골라 주세요.",
            "Can't open the song file. Please pick it again.",
        )
        is JobFailedException -> tr(
            "이 곡은 악보로 만들지 못했어요. 다시 시도하면 처음부터 다시 만들어요.",
            "We couldn't make scores for this song. Retry to start over.",
        )
        is ApiException -> when (e.code) {
            401 -> tr("ROCKY에 접속할 수 없어요. 연결 설정을 확인해 주세요.", "Can't sign in to ROCKY. Check the connection settings.")
            413 -> tr("곡 파일이 너무 커요. 더 짧은 곡이나 MP3로 올려 주세요.", "The file is too big. Try a shorter song or an MP3.")
            415 -> tr("MP3나 WAV 파일만 올릴 수 있어요.", "Only MP3 or WAV files can be used.")
            422 -> tr(
                "원곡에 기타가 없으면 기타는 1대까지만 만들 수 있어요.",
                "If the song has no guitar, we can add only one guitar.",
            )
            404 -> tr("이 곡을 찾을 수 없어요. 다시 시도하면 처음부터 다시 만들어요.", "We lost this song. Retry to start over.")
            // 오류 번호는 보여주지 않는다 (Nielsen 9: 쉬운 말로, 해결 방법과 함께).
            else -> tr("잠시 문제가 생겼어요. 잠시 뒤에 다시 시도해 주세요.", "Something went wrong. Please retry in a moment.")
        }
        is IOException -> tr(
            "인터넷에 연결할 수 없어요. 연결을 확인한 뒤 다시 시도해 주세요.",
            "Can't connect. Check your internet and retry.",
        )
        else -> tr("알 수 없는 문제가 생겼어요. 다시 시도해 주세요.", "Something went wrong. Please retry.")
    }
}

/** 고른 음원 파일을 더 이상 열 수 없을 때 (파일이 지워졌거나 읽기 권한이 사라짐). */
class FileGoneException : IOException("audio file is gone")
