@file:OptIn(ExperimentalMaterial3Api::class)

package com.team3.rocky

import androidx.compose.runtime.LaunchedEffect
import com.team3.rocky.server.ServerCleanup
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.IntrinsicSize
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.basicMarquee
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.team3.rocky.auth.AccountScreen
import com.team3.rocky.auth.AuthRepository
import com.team3.rocky.auth.LoginScreen
import com.team3.rocky.auth.SignUpScreen
import com.team3.rocky.auth.User
import com.team3.rocky.band.BandDetailScreen
import com.team3.rocky.band.BandJoinScreen
import com.team3.rocky.band.BandListScreen
import com.team3.rocky.band.BandRepository
import com.team3.rocky.band.PickScoreScreen
import com.team3.rocky.band.ShareToBandScreen
import com.team3.rocky.progress.AudioFile
import com.team3.rocky.progress.ScoreJob
import com.team3.rocky.progress.JobNotifier
import com.team3.rocky.progress.ScoreJobs
import com.team3.rocky.progress.Stage
import com.team3.rocky.progress.formatEta
import com.team3.rocky.server.RockyApi
import com.team3.rocky.server.ScoreStore
import com.team3.rocky.band.SharedScore
import com.team3.rocky.server.ServerSettings
import com.team3.rocky.server.Backend
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// ---------- 화면 목록 ----------
sealed class Screen {
    object Login : Screen()                                       // 0. 로그인
    object SignUp : Screen()                                      // 0-1. 회원가입
    object Account : Screen()                                     // 0-2. 내 정보
    object Main : Screen()                                        // 1. 하단 탭 (홈 / 만드는 중 / 보관함 / 내 밴드)
    object Lineup : Screen()                                      // 2. 우리 밴드 구성 (1/2단계)
    object Upload : Screen()                                      // 3. 곡 올리기 (2/2단계) → 악보 만들기 시작
    // 5. 결과. 밴드에서 열면 myPart(이 밴드에서 내 파트) 악보를 먼저 보여준다.
    class Result(val work: Work, val myPart: String? = null, val jobId: Long? = null) : Screen()
    object BandJoin : Screen()                                    // 7-1. 밴드 만들기·참여
    class BandDetail(val bandId: Long) : Screen()                 // 7-2. 밴드 상세
    class ShareToBand(val work: Work) : Screen()                  // 7-3. 결과 → 밴드에 공유
    class PickScore(val bandId: Long) : Screen()                  // 7-4. 밴드 → 보관함 악보 공유
}

/**
 * '기타 대수 바꿔서 다시 만들기'. 원곡 악기는 사용자에게 묻지 않고 모델이 판단하지만,
 * 기타 대수가 틀려 보이면 사용자가 0~2대를 고르고 우리 밴드 구성·곡 올리기부터 다시 만든다
 * (서버는 올린 음원을 남기지 않아서 곡을 다시 올려야 한다).
 * [original]은 첫 결과에서 모델이 찾은 기타 아닌 원곡 악기 + 고른 기타 대수 → 서버의 원곡 구성으로 보낸다.
 */
data class GuitarRedo(val title: String, val guitars: Int, val original: List<String>)

enum class Tab(private val ko: String, private val en: String) {
    NEW("홈", "Home"), PROGRESS("만드는 중", "In progress"), STORAGE("보관함", "Library"), BANDS("내 밴드", "Bands");

    val label get() = tr(ko, en)
}

@Composable
fun RockyApp() {
    val ctx = LocalContext.current
    // 처음 켤 때: 이용 약관에 동의해야 앱을 쓸 수 있다. 그다음 사용 안내 슬라이드 ('다시 보지 않기' 전까지 켤 때마다 한 번).
    var termsOk by remember { mutableStateOf(FirstRun.termsAgreed(ctx)) }
    if (!termsOk) {
        TermsScreen(onAgree = { FirstRun.agreeTerms(ctx); termsOk = true })
        return
    }
    var guide by remember { mutableStateOf(!FirstRun.guideOff(ctx) && !FirstRun.guideShownThisRun) }
    if (guide) OnboardingDialog(onDone = { FirstRun.guideShownThisRun = true; guide = false })
    val auth = remember { AuthRepository(ctx) }
    val bands: BandRepository = remember { Backend.bands(ctx) }
    // 앱을 켤 때 로그인 상태가 남아 있으면 바로 홈, 아니면 로그인 화면에서 시작한다.
    var user by remember { mutableStateOf(auth.currentUser()) }
    val stack = remember { mutableStateListOf(if (user != null) Screen.Main else Screen.Login) }
    var tab by remember { mutableStateOf(Tab.NEW) }
    var lineup by remember { mutableStateOf(setOf<String>()) }
    // '기타 대수 바꿔서 다시 만들기' 중이면 그 정보. 보통 새 악보는 null (원곡 악기는 모델이 판단).
    var redo by remember { mutableStateOf<GuitarRedo?>(null) }
    // 프로필 사진을 바꾸면 숫자를 올려서 다시 읽게 한다.
    var photoVersion by remember { mutableIntStateOf(0) }
    val appScope = androidx.compose.runtime.rememberCoroutineScope()

    fun go(s: Screen) { stack.add(s) }
    fun back() { if (stack.size > 1) stack.removeAt(stack.lastIndex) }
    // 로그인·로그아웃 뒤에는 이전 화면으로 돌아갈 수 없게 쌓인 화면을 비운다.
    // Keep the navigation stack nonempty while Compose observes each update.
    fun restart(s: Screen) {
        stack.add(s)
        while (stack.size > 1) stack.removeAt(0)
    }
    fun signedIn(u: User) { user = u; tab = Tab.NEW; restart(Screen.Main) }
    fun newScore(preset: Set<String>) { redo = null; lineup = preset; go(Screen.Lineup) }
    // 기타 대수를 고른 뒤: 우리 밴드 구성(지난번 그대로 채워 둠)과 곡 올리기를 거쳐 처음부터 다시 만든다.
    fun redoGuitars(work: Work, plan: GuitarRedo) { redo = plan; lineup = work.instruments.toSet(); go(Screen.Lineup) }
    // 안드로이드 13 이상: 앱을 안 보는 동안 멈추면 알림으로 알리려면 허용이 필요하다. 악보를 만들기 시작할 때 묻는다.
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    fun openTab(t: Tab) { tab = t; restart(Screen.Main) }

    // 다른 밴드원이 공유한 악보는 이 폰에 파일이 없으므로, 처음 열 때 서버에서 받는다.
    var fetching by remember { mutableStateOf(false) }
    fun openShared(score: SharedScore, part: String?) {
        val job = score.jobId
        if (job == null || ScoreStore.load(ctx, score.work.id) != null) {
            go(Screen.Result(score.work, myPart = part)); return
        }
        fetching = true
        appScope.launch {
            val ok = withContext(Dispatchers.IO) {
                runCatching { ScoreStore.download(ctx, RockyApi.from(ctx), job, score.work.id) }.isSuccess
            }
            fetching = false
            if (ok) go(Screen.Result(score.work, myPart = part))
            else Toast.makeText(
                ctx, tr("악보를 받지 못했어요. 인터넷이나 연결 설정을 확인해 주세요", "Couldn't get the score. Check the internet or connection settings"),
                Toast.LENGTH_LONG,
            ).show()
        }
    }
    if (fetching) AlertDialog(
        onDismissRequest = {},
        title = { Text(tr("악보 받는 중", "Getting the score")) },
        text = { Text(tr("밴드에 공유된 악보를 받고 있어요…", "Downloading the score shared with your band…")) },
        confirmButton = {},
    )

    // 탭 화면에서 뒤로가기를 누르면 먼저 '새 악보' 탭으로 돌아간다.
    BackHandler(enabled = stack.size > 1 || (stack.last() == Screen.Main && tab != Tab.NEW)) {
        if (stack.size > 1) back() else tab = Tab.NEW
    }

    // 악보 만들기가 실패하면 어느 화면에 있든 팝업으로 알린다.
    // (앱을 안 보고 있었다면 휴대폰 알림도 갔고, 돌아왔을 때 이 팝업이 보인다.)
    // - 이 곡 그대로 다시 할 수 있으면 '다시 시도' (서버가 기다리라고 하면 남은 초를 세고 나서)
    // - 아니면 곡은 이미 목록에서 빠졌고 '새로 만들기'로 우리 밴드 구성·곡 올리기부터 다시 한다.
    val stoppedJob = ScoreJobs.stopped
    if (stoppedJob != null && user != null) {
        val wait = retryCountdown(stoppedJob)
        AlertDialog(
            onDismissRequest = { ScoreJobs.stopped = null },
            icon = { WarnIcon(MaterialTheme.colorScheme.error, 28.dp) },
            title = {
                Text(
                    if (stoppedJob.rejected) tr("이 곡으로는 악보를 만들 수 없어요", "Can't make scores from this song")
                    else tr("악보를 만들지 못했어요", "Couldn't make the scores"),
                    textAlign = TextAlign.Center,
                )
            },
            text = {
                Column {
                    Text("'${stoppedJob.title}'", fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(6.dp))
                    Text(stoppedJob.error ?: tr("문제가 생겼어요.", "Something went wrong."), lineHeight = 20.sp)
                    if (!stoppedJob.retryable) {
                        Spacer(Modifier.height(8.dp))
                        Text(
                            tr("목록에서 뺐어요. 새로 만들기에서 처음부터 다시 할 수 있어요.",
                                "Removed from the list. You can start over with a new score."),
                            fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, lineHeight = 18.sp,
                        )
                    }
                }
            },
            confirmButton = {
                if (stoppedJob.retryable) {
                    TextButton(enabled = wait == 0, onClick = { val j = stoppedJob; ScoreJobs.stopped = null; ScoreJobs.retry(ctx, j) }) {
                        Text(if (wait > 0) tr("${wait}초 뒤 다시 시도", "Retry in ${wait}s") else tr("다시 시도", "Retry"))
                    }
                } else {
                    TextButton(onClick = {
                        val j = stoppedJob; ScoreJobs.stopped = null
                        // 같은 우리 밴드 구성으로 채워 두고 1단계부터. 거절된 곡이면 다른 곡을 고르면 된다.
                        newScore(j.lineup.toSet())
                    }) { Text(tr("새로 만들기", "New score")) }
                }
            },
            dismissButton = {
                // 다시 시도할 수 있는 곡은 닫아도 '만드는 중' 탭의 그 곡 카드에 이유와 '다시 시도'가 남아 있다.
                TextButton(onClick = { ScoreJobs.stopped = null }) {
                    Text(tr("닫기", "Close"), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            },
        )
    }

    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        when (val s = stack.last()) {
            Screen.Login -> LoginScreen(auth, onLoggedIn = ::signedIn, onSignUp = { go(Screen.SignUp) })
            Screen.SignUp -> SignUpScreen(auth, onBack = { back() }, onSignedUp = ::signedIn)
            Screen.Account -> user?.let { u ->
                AccountScreen(
                    u, auth, photoVersion,
                    onBack = { back() },
                    onUpdated = { updated ->
                        user = updated
                        photoVersion++
                        appScope.launch { bands.updateNickname(updated) }
                    },
                    onLogout = { auth.logout(); ScoreJobs.clear(ctx); user = null; restart(Screen.Login) },
                )
            }
            Screen.Main -> user?.let { u ->
                MainTabs(
                    user = u, bands = bands, tab = tab, photoVersion = photoVersion,
                    onTab = { tab = it },
                    onAccount = { go(Screen.Account) },
                    // 회원 정보에 적은 악기를 새 악보의 기본 구성으로 쓴다.
                    onNew = { newScore(Demo.lineupOf(u.instruments)) },
                    onOpenJob = { job -> go(Screen.Result(job.toWork(), jobId = job.id)) },
                    onOpenWork = { go(Screen.Result(it)) },
                    onOpenBand = { go(Screen.BandDetail(it)) },
                    onAddBand = { go(Screen.BandJoin) },
                )
            }
            Screen.Lineup -> {
                val plan = redo
                // 파이프라인 규칙: 원곡에 기타가 없으면 우리 밴드 기타는 1대까지만 새로 만들 수 있다 (AT3).
                val blocked = if (plan != null && plan.guitars == 0 && Demo.guitarCount(lineup) == 2) tr(
                    "원곡에 기타가 없으면 기타는 1대까지만 만들 수 있어요. 기타 2를 빼 주세요.",
                    "With no guitar in the song, only one guitar part can be made. Remove Guitar 2.",
                ) else null
                BandStageScreen(
                    lineup = lineup,
                    onChange = { lineup = it },
                    onBack = { back() },
                    onNext = { go(Screen.Upload) },
                    notice = plan?.let { guitarRedoNotice(it) },
                    blocked = blocked,
                )
            }
            Screen.Upload -> UploadScreen(
                redo = redo,
                onBack = { back() },
                onStart = { title, audio ->
                    // 원곡 악기는 묻지 않는다: 보통은 비워서 보내고(모델이 판단),
                    // 기타 대수를 바꿔 다시 만들 때만 모델이 찾은 악기 + 고른 기타 대수를 보낸다.
                    ScoreJobs.start(ctx, title, Demo.ordered(lineup), redo?.original.orEmpty(), audio = audio)
                    redo = null
                    if (JobNotifier.needsPermission(ctx)) askNotifications.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                    openTab(Tab.PROGRESS)
                },
            )
            is Screen.Result -> ResultScreen(
                work = s.work,
                myPart = s.myPart,
                onBack = { back() },
                onSaved = { s.jobId?.let { ScoreJobs.find(it) }?.saved = true },
                onShareToBand = { go(Screen.ShareToBand(s.work)) },
                onRedoGuitars = { plan -> redoGuitars(s.work, plan) },
            )

            // ---------- 나의 밴드 ----------
            Screen.BandJoin -> user?.let { u ->
                BandJoinScreen(u, bands, onBack = { back() }, onDone = { id ->
                    // 만들기·참여 화면은 뒤로가기에서 빼고 바로 밴드 상세로 간다.
                    stack.removeAt(stack.lastIndex)
                    go(Screen.BandDetail(id))
                })
            }
            is Screen.BandDetail -> user?.let { u ->
                BandDetailScreen(
                    u, bands, s.bandId,
                    onBack = { back() },
                    onOpenScore = { score, part -> openShared(score, part) },
                    onShareScore = { go(Screen.PickScore(s.bandId)) },
                    // 밴드 멤버들이 맡은 파트를 새 악보의 기본 구성으로 쓴다.
                    onNewScore = { parts -> newScore(Demo.lineupOf(parts)) },
                    onLeft = { back() },
                )
            }
            is Screen.ShareToBand -> user?.let { u ->
                ShareToBandScreen(
                    u, bands, s.work,
                    onBack = { back() },
                    onShared = { back() },
                    onAddBand = { go(Screen.BandJoin) },
                )
            }
            is Screen.PickScore -> user?.let { u ->
                PickScoreScreen(u, bands, s.bandId, onBack = { back() })
            }
        }
    }
}

// ---------- 공통 화면 틀 ----------
@Composable
fun Page(
    title: String,
    onBack: (() -> Unit)?,
    modifier: Modifier = Modifier,
    bottom: (@Composable () -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {},
    /** 위 제목 줄, 아래 버튼 줄과 내용 사이에 구분선을 넣는다. */
    dividers: Boolean = false,
    content: @Composable ColumnScope.() -> Unit,
) {
    val cs = MaterialTheme.colorScheme
    Scaffold(
        modifier = modifier,
        containerColor = cs.background,
        topBar = {
            Column {
                TopAppBar(
                    // 긴 제목은 옆으로 흘러가며 끝까지 보여준다.
                    title = { Text(title, fontWeight = FontWeight.Bold, maxLines = 1, modifier = Modifier.basicMarquee()) },
                    navigationIcon = {
                        if (onBack != null) TextButton(onClick = onBack) {
                            Text("←", fontSize = 22.sp, modifier = Modifier.semantics { contentDescription = tr("뒤로", "Back") })
                        }
                    },
                    actions = actions,
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = cs.background),
                )
                if (dividers) HorizontalDivider(color = cs.outlineVariant)
            }
        },
        bottomBar = {
            if (bottom != null) Column {
                if (dividers) HorizontalDivider(color = cs.outlineVariant)
                // 갤럭시의 홈·뒤로 버튼 줄(내비게이션 바)에 버튼이 가리지 않게 그 높이만큼 띄운다.
                // 내비게이션 바가 0으로 오는 기기(제스처 막대를 숨긴 갤럭시 등)도 있어서 아래 여백을 넉넉히 둔다.
                Box(
                    Modifier.windowInsetsPadding(BottomSystemBars)
                        .padding(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 20.dp),
                ) { bottom() }
            }
        },
    ) { pad ->
        Column(
            Modifier.padding(pad).consumeWindowInsets(pad).fillMaxSize().padding(horizontal = 20.dp),
            content = content,
        )
    }
}

/** 이름 바꾸기 등에 쓰는 한 줄 입력 창. */
@Composable
fun TextInputDialog(
    title: String,
    initial: String,
    label: String,
    maxLength: Int,
    emoji: Boolean = false,
    validate: (String) -> String? = { if (it.isBlank()) tr("내용을 입력해 주세요", "Please type something") else null },
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit,
) {
    var value by remember { mutableStateOf(initial) }
    val error = validate(value)
    fun limit(s: String) = if (s.codePointCount(0, s.length) <= maxLength) s
    else s.substring(0, s.offsetByCodePoints(0, maxLength))
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column {
                OutlinedTextField(
                    value = value, onValueChange = { value = limit(it) }, label = { Text(label) },
                    singleLine = true, isError = error != null && value.isNotEmpty(),
                    supportingText = {
                        Text(error.takeIf { value.isNotEmpty() } ?: "${value.trim().codePointCount(0, value.trim().length)} / $maxLength")
                    },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    modifier = Modifier.fillMaxWidth(),
                )
                if (emoji) EmojiRow { value = limit(value + it) }
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(value.trim()) }, enabled = error == null) { Text(tr("저장", "Save")) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(tr("취소", "Cancel")) } },
    )
}

/** 누르면 이모티콘을 입력칸에 붙인다. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun EmojiRow(onPick: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        QUICK_EMOJI.forEach { e ->
            Box(
                Modifier.size(38.dp).clip(RoundedCornerShape(10.dp)).background(cs.surfaceVariant).clickable { onPick(e) },
                contentAlignment = Alignment.Center,
            ) { Text(e, fontSize = 18.sp) }
        }
    }
}

/** 안내 문구. 회색 작은 글씨 대신 배경이 있는 상자에 또렷한 글씨로 보여준다. */
@Composable
fun InfoNote(text: String, modifier: Modifier = Modifier, strong: Boolean = false) {
    val cs = MaterialTheme.colorScheme
    Text(
        text,
        fontSize = 14.sp, lineHeight = 20.sp,
        fontWeight = if (strong) FontWeight.Bold else FontWeight.Medium,
        color = if (strong) cs.primary else cs.onSurface,
        modifier = modifier.fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(if (strong) cs.primary.copy(alpha = 0.12f) else cs.surfaceVariant)
            .padding(horizontal = 14.dp, vertical = 10.dp),
    )
}

// ---------- 1. 하단 탭 ----------
@Composable
fun MainTabs(
    user: User,
    bands: BandRepository,
    tab: Tab,
    photoVersion: Int,
    onTab: (Tab) -> Unit,
    onAccount: () -> Unit,
    onNew: () -> Unit,
    onOpenJob: (ScoreJob) -> Unit,
    onOpenWork: (Work) -> Unit,
    onOpenBand: (Long) -> Unit,
    onAddBand: () -> Unit,
) {
    val cs = MaterialTheme.colorScheme
    Scaffold(
        containerColor = cs.background,
        bottomBar = {
            // 하단 탭이 갤럭시 홈·뒤로 버튼 줄에 가리지 않게 그 높이만큼 위로 올린다.
            NavigationBar(containerColor = cs.surfaceContainer, windowInsets = BottomSystemBars) {
                Tab.entries.forEach { t ->
                    NavigationBarItem(
                        selected = t == tab,
                        onClick = { onTab(t) },
                        icon = {
                            val running = ScoreJobs.runningCount
                            if (t == Tab.PROGRESS && running > 0) {
                                BadgedBox(badge = { Badge { Text("$running") } }) { TabIcon(t, t == tab) }
                            } else TabIcon(t, t == tab)
                        },
                        label = { Text(t.label, fontSize = 12.sp, maxLines = 1) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = cs.primary, selectedTextColor = cs.primary,
                            indicatorColor = cs.primary.copy(alpha = 0.16f),
                            unselectedIconColor = cs.onSurfaceVariant, unselectedTextColor = cs.onSurfaceVariant,
                        ),
                    )
                }
            }
        },
    ) { pad ->
        val inner = Modifier.padding(pad).consumeWindowInsets(pad)
        when (tab) {
            Tab.NEW -> HomeTab(user, photoVersion, inner, onAccount, onNew)
            Tab.PROGRESS -> ProgressTab(inner, onOpenJob, onNew)
            Tab.STORAGE -> StorageTab(inner, onOpenWork)
            Tab.BANDS -> BandListScreen(user, bands, onBack = null, onOpen = onOpenBand, onAdd = onAddBand, modifier = inner)
        }
    }
}

/** 하단 탭 아이콘. 선택 여부에 따라 색이 바뀌도록 한 가지 색으로 그린다. */
@Composable
private fun TabIcon(tab: Tab, selected: Boolean) {
    val c = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
    Canvas(Modifier.size(24.dp)) {
        val u = size.minDimension / 24f
        val s = Stroke(width = 1.9f * u, cap = StrokeCap.Round)
        when (tab) {
            Tab.NEW -> {
                drawRoundRect(c, Offset(4 * u, 2.5f * u), Size(16 * u, 19 * u), CornerRadius(2.5f * u), style = s)
                drawLine(c, Offset(12 * u, 8 * u), Offset(12 * u, 16 * u), s.width, StrokeCap.Round)
                drawLine(c, Offset(8 * u, 12 * u), Offset(16 * u, 12 * u), s.width, StrokeCap.Round)
            }
            Tab.PROGRESS -> {
                drawCircle(c, 9 * u, Offset(12 * u, 12 * u), style = s)
                drawLine(c, Offset(12 * u, 12 * u), Offset(12 * u, 7 * u), s.width, StrokeCap.Round)
                drawLine(c, Offset(12 * u, 12 * u), Offset(15.5f * u, 14 * u), s.width, StrokeCap.Round)
            }
            Tab.STORAGE -> {
                drawRoundRect(c, Offset(3 * u, 8 * u), Size(18 * u, 13 * u), CornerRadius(2 * u), style = s)
                drawLine(c, Offset(5 * u, 4.5f * u), Offset(19 * u, 4.5f * u), s.width, StrokeCap.Round)
                drawLine(c, Offset(9 * u, 13 * u), Offset(15 * u, 13 * u), s.width, StrokeCap.Round)
            }
            Tab.BANDS -> {
                drawCircle(c, 3.2f * u, Offset(9 * u, 8 * u), style = s)
                drawArc(c, 180f, 180f, false, Offset(3 * u, 14 * u), Size(12 * u, 10 * u), style = s)
                drawCircle(c, 2.6f * u, Offset(17 * u, 9 * u), style = s)
                drawArc(c, 200f, 140f, false, Offset(13 * u, 15 * u), Size(9 * u, 8 * u), style = s)
            }
        }
    }
}

// ---------- 1-1. 홈 ----------
/**
 * 홈: 인사, 큰 제목, 큰 '새 악보 만들기' 버튼, 접어 둔 '이렇게 만들어요'.
 * (정확도 팁과 만드는 중인 곡은 홈에서 뺐다. 만드는 중인 곡은 '만드는 중' 탭과 아래 탭의 숫자로 본다.)
 */
@Composable
fun HomeTab(
    user: User,
    photoVersion: Int,
    modifier: Modifier,
    onAccount: () -> Unit,
    onNew: () -> Unit,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val photo = remember(photoVersion, user.id) { ProfileStore.load(ctx, user.id) }
    var howOpen by remember { mutableStateOf(false) }
    var guide by remember { mutableStateOf(false) }
    if (guide) OnboardingDialog(onDone = { guide = false })

    Column(modifier.fillMaxSize().statusBarsPadding().verticalScroll(rememberScrollState()).padding(24.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(tr("${user.nickname}님, 반가워요", "Hi, ${user.nickname}"), color = cs.onSurfaceVariant,
                modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            // 오른쪽 위 프로필을 누르면 내 정보(수정·화면 모드·언어·로그아웃)로 간다.
            Row(
                Modifier.clip(RoundedCornerShape(20.dp)).clickable(onClick = onAccount).padding(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(tr("내 정보", "Profile"), fontSize = 13.sp, color = cs.onSurfaceVariant)
                Spacer(Modifier.width(8.dp))
                Avatar(photo, user.nickname, 36.dp)
            }
        }
        Spacer(Modifier.height(20.dp))
        Text(
            tr("오늘은 어떤 곡을\n합주하나요?", "What are you\nplaying today?"),
            fontSize = 30.sp, lineHeight = 38.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.6).sp,
        )
        Spacer(Modifier.height(24.dp))
        NewScoreButton(onNew)

        // 처음 쓰는 사람을 위한 순서 안내. 평소에는 접어 두고 눌러서 편다.
        Spacer(Modifier.height(16.dp))
        Column(Modifier.fillMaxWidth().card(RoundedCornerShape(18.dp), cs)) {
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).clickable { howOpen = !howOpen }
                    .padding(horizontal = 18.dp, vertical = 16.dp)
                    .semantics { contentDescription = if (howOpen) tr("이렇게 만들어요 접기", "Hide how it works") else tr("이렇게 만들어요 펼치기", "Show how it works") },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(tr("이렇게 만들어요", "How it works"), fontWeight = FontWeight.Bold, fontSize = 16.sp, modifier = Modifier.weight(1f))
                Chevron(open = howOpen, color = cs.onSurfaceVariant)
            }
            if (howOpen) {
                Column(Modifier.fillMaxWidth().padding(start = 18.dp, end = 18.dp, bottom = 8.dp)) {
                    HowStep("1", tr("우리 밴드 악기 고르기", "Pick your band's instruments"),
                        tr("우리 밴드에 있는 악기를 골라요", "Choose the instruments your band plays"))
                    HowStep("2", tr("곡 올리기", "Upload a song"),
                        tr("MP3나 WAV 파일을 올려요", "Upload an MP3 or WAV file"))
                    HowStep("3", tr("나만의 악보 받기", "Get your own scores"),
                        tr("우리 밴드 파트별 악보가 나와요", "Get a score for each part in your band"), last = true)
                    TextButton(onClick = { guide = true }) {
                        Text(tr("처음 안내 다시 보기", "See the intro again"), fontSize = 13.sp, color = cs.primary)
                    }
                }
            }
        }
        Spacer(Modifier.height(8.dp))
    }
}

/** 홈의 큰 '새 악보 만들기' 버튼. */
@Composable
private fun NewScoreButton(onClick: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(24.dp)
    Column(
        Modifier.fillMaxWidth().heightIn(min = 168.dp)
            .card(shape, cs, bg = cs.primary, line = cs.primary)
            .clickable(onClick = onClick)
            .semantics { contentDescription = tr("새 악보 만들기", "Make a new score") }
            .padding(22.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
            Box(
                Modifier.size(52.dp).clip(androidx.compose.foundation.shape.CircleShape).background(cs.onPrimary.copy(alpha = 0.14f)),
                contentAlignment = Alignment.Center,
            ) { Text("＋", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = cs.onPrimary) }
            Spacer(Modifier.weight(1f))
            Text("→", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = cs.onPrimary)
        }
        Spacer(Modifier.height(18.dp))
        Text(tr("새 악보 만들기", "Make a new score"), fontSize = 26.sp, fontWeight = FontWeight.ExtraBold,
            color = cs.onPrimary, letterSpacing = (-0.4).sp)
        Spacer(Modifier.height(4.dp))
        Text(tr("곡을 올리면 우리 밴드 파트별 악보가 나와요", "Upload a song, get a score for every part"),
            fontSize = 14.sp, color = cs.onPrimary.copy(alpha = 0.8f), lineHeight = 19.sp)
    }
}

/** 접기·펴기 화살표. 열리면 위를 본다. */
@Composable
private fun Chevron(open: Boolean, color: Color) {
    Canvas(Modifier.size(20.dp)) {
        val u = size.minDimension / 20f
        val y1 = if (open) 12.5f else 7.5f
        val y2 = if (open) 7.5f else 12.5f
        drawLine(color, Offset(5 * u, y1 * u), Offset(10 * u, y2 * u), 2f * u, StrokeCap.Round)
        drawLine(color, Offset(10 * u, y2 * u), Offset(15 * u, y1 * u), 2f * u, StrokeCap.Round)
    }
}

@Composable
private fun HowStep(no: String, title: String, sub: String, last: Boolean = false) {
    val cs = MaterialTheme.colorScheme
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
        // 왼쪽: 번호 원과, 다음 단계로 이어지는 선
        Column(Modifier.width(30.dp).fillMaxHeight(), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                Modifier.size(30.dp).clip(androidx.compose.foundation.shape.CircleShape).background(cs.primary),
                contentAlignment = Alignment.Center,
            ) { Text(no, fontWeight = FontWeight.ExtraBold, fontSize = 14.sp, color = cs.onPrimary) }
            if (!last) {
                Box(Modifier.padding(vertical = 4.dp).width(2.dp).weight(1f).clip(RoundedCornerShape(1.dp)).background(cs.primary.copy(alpha = 0.35f)))
            }
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f).padding(top = 4.dp, bottom = if (last) 6.dp else 18.dp)) {
            Text(title, fontSize = 15.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(2.dp))
            Text(sub, fontSize = 13.sp, color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

/** 경고 아이콘 (실패 팝업·카드). 둥근 삼각형 안에 느낌표. */
@Composable
fun WarnIcon(color: Color, size: androidx.compose.ui.unit.Dp) {
    Canvas(Modifier.size(size)) {
        val u = this.size.minDimension / 24f
        val s = Stroke(width = 1.9f * u, cap = StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round)
        val tri = Path().apply {
            moveTo(12f * u, 3f * u); lineTo(22f * u, 20.5f * u); lineTo(2f * u, 20.5f * u); close()
        }
        drawPath(tri, color, style = s)
        drawLine(color, Offset(12f * u, 9.5f * u), Offset(12f * u, 14f * u), 2.1f * u, StrokeCap.Round)
        drawCircle(color, 1.25f * u, Offset(12f * u, 17.2f * u))
    }
}

/** '다시 시도'를 누를 수 있을 때까지 남은 초. 0이면 바로 누를 수 있다. 1초마다 다시 그린다. */
@Composable
fun retryCountdown(job: ScoreJob): Int {
    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(job, job.retryAt) {
        while (true) {
            now = System.currentTimeMillis()
            if (now >= job.retryAt) break
            delay(250)
        }
    }
    return ((job.retryAt - now + 999) / 1000).coerceAtLeast(0).toInt()
}

/** 기타 대수를 바꿔 다시 만들 때 1·2단계 위에 보여줄 안내. */
fun guitarRedoNotice(plan: GuitarRedo): String {
    val n = when (plan.guitars) { 0 -> tr("없음", "none"); 1 -> tr("1대", "1"); else -> tr("2대", "2") }
    return tr("'${plan.title}'을(를) 원곡 기타 ${n}로 다시 만들어요", "Remaking '${plan.title}' with original guitars: $n")
}

@Composable
fun BigCard(title: String, sub: String, bg: Color, fg: Color, onClick: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(18.dp)
    Row(
        Modifier.fillMaxWidth()
            .card(shape, cs, bg = bg, line = if (bg == cs.primary) bg else cs.outlineVariant)
            .clickable(onClick = onClick)
            .padding(start = 20.dp, top = 20.dp, bottom = 20.dp, end = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, fontSize = 20.sp, fontWeight = FontWeight.ExtraBold, color = fg, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(4.dp))
            Text(sub, fontSize = 13.sp, color = fg.copy(alpha = 0.75f), lineHeight = 18.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Spacer(Modifier.width(12.dp))
        Box(
            Modifier.size(44.dp).clip(androidx.compose.foundation.shape.CircleShape).background(fg.copy(alpha = 0.12f)),
            contentAlignment = Alignment.Center,
        ) { Text("→", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = fg) }
    }
}

@Composable
fun WorkRow(w: Work, onClick: () -> Unit, trailing: @Composable RowScope.() -> Unit = {}) {
    val cs = MaterialTheme.colorScheme
    Row(
        Modifier.fillMaxWidth()
            .card(RoundedCornerShape(16.dp), cs)
            .clickable(onClick = onClick)
            .padding(start = 18.dp, top = 14.dp, bottom = 14.dp, end = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(w.title, fontWeight = FontWeight.Bold, fontSize = 17.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(4.dp))
            Text(Demo.labels(w.instruments), fontSize = 13.sp, color = cs.onSurfaceVariant, maxLines = 1)
            Text(w.date, fontSize = 12.sp, color = cs.onSurfaceVariant)
        }
        trailing()
    }
}

// ---------- 1-2. 만드는 중 ----------
@Composable
fun ProgressTab(modifier: Modifier, onOpen: (ScoreJob) -> Unit, onNew: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val jobs = ScoreJobs.jobs
    Page(tr("만드는 중", "In progress"), onBack = null, modifier = modifier) {
        if (jobs.isEmpty()) {
            Spacer(Modifier.height(80.dp))
            Text(
                tr("만들고 있는 악보가 없어요.",
                    "Nothing in progress."),
                color = cs.onSurfaceVariant, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(20.dp))
            OutlinedButton(shape = ButtonShape, onClick = onNew, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                Text(tr("새 악보 만들기", "Make a new score"))
            }
        } else {
            InfoNote(tr("ROCKY는 백그라운드에서 돌아가요. 다른 앱을 써도 계속 만들고, 다 되거나 실패하면 알려 드려요.",
                "ROCKY works in the background. Use other apps; we'll tell you when it's done or fails."))
            Spacer(Modifier.height(12.dp))
            LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(jobs, key = { it.id }) { job -> JobCard(job, onOpen = { onOpen(job) }) }
                item { Spacer(Modifier.height(12.dp)) }
            }
        }
    }
}

@Composable
private fun JobCard(job: ScoreJob, onOpen: () -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val p = job.progress
    // 서버 값은 2초마다·단계마다 뛰므로, 0.1초마다 조금씩 일정하게 올린다 (progress/SmoothProgress).
    var shown by remember(job.id) { mutableFloatStateOf(job.bar.shown) }
    LaunchedEffect(job.id) {
        var last = System.nanoTime()
        while (true) {
            val now = System.nanoTime()
            if (!job.failed) shown = job.bar.step(job.progress, (now - last) / 1_000_000_000f)
            last = now
            if (job.done) break
            delay(100)
        }
    }
    var confirm by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth()
            .card(RoundedCornerShape(18.dp), cs)
            .border(
                BorderStroke(1.dp, when {
                    job.failed -> cs.error
                    job.done && !job.saved -> cs.primary
                    else -> Color.Transparent
                }),
                RoundedCornerShape(18.dp),
            )
            .clickable(enabled = job.done, onClick = onOpen)
            .padding(18.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(job.title, fontWeight = FontWeight.Bold, fontSize = 16.sp, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            Text(
                "${(shown * 100).toInt()}%", fontSize = 22.sp, fontWeight = FontWeight.Black, color = cs.primary,
            )
        }
        Text(Demo.labels(job.lineup), fontSize = 12.sp, color = cs.onSurfaceVariant, maxLines = 1)
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)).background(cs.surfaceVariant)) {
            Box(Modifier.fillMaxWidth(shown).height(8.dp).background(if (job.failed) cs.error else cs.primary))
        }
        Spacer(Modifier.height(10.dp))
        val err = job.error
        val cancelError = job.cancelError
        if (cancelError != null) {
            Text(cancelError, fontSize = 13.sp, color = cs.error)
            Spacer(Modifier.height(8.dp))
        }
        if (err != null) {
            // 이 카드에 남는 실패는 이 곡 그대로 다시 시도할 수 있는 것뿐이다 (나머지는 목록에서 빠지고 팝업으로 알린다).
            Row(verticalAlignment = Alignment.CenterVertically) {
                WarnIcon(cs.error, 18.dp)
                Spacer(Modifier.width(6.dp))
                Text(tr("악보를 만들지 못했어요", "Couldn't make the scores"), fontWeight = FontWeight.Bold, color = cs.error, fontSize = 14.sp)
            }
            Spacer(Modifier.height(2.dp))
            Text(err, fontSize = 13.sp, color = cs.onSurface, lineHeight = 18.sp)
            if (job.retryable) {
                val wait = retryCountdown(job)
                Spacer(Modifier.height(8.dp))
                Button(
                    shape = ButtonShape, onClick = { ScoreJobs.retry(ctx, job) }, enabled = wait == 0,
                    modifier = Modifier.fillMaxWidth().height(44.dp), contentPadding = TightButtonPadding,
                ) {
                    Text(if (wait > 0) tr("${wait}초 뒤 다시 시도할 수 있어요", "Retry in ${wait}s") else tr("다시 시도", "Retry"), fontSize = 14.sp, maxLines = 1)
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                when {
                    err != null -> ""
                    job.done && job.saved -> tr("보관함에 저장됨", "Saved to library")
                    job.done -> tr("눌러서 악보 보기 →", "Tap to open →")
                    job.phase != null -> job.phase!!
                    p == null -> tr("준비 중", "Getting ready")
                    else -> "${p.stage.index}/${Stage.entries.size} ${p.stage.title}"
                },
                fontSize = 13.sp, fontWeight = if (job.done) FontWeight.Bold else FontWeight.Normal,
                color = if (job.done && !job.saved) cs.primary else cs.onSurface,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            if (!job.done && err == null && job.phase == null) {
                Text(formatEta(p?.etaSec), fontSize = 12.sp, color = cs.onSurfaceVariant, maxLines = 1)
            }
            TextButton(onClick = { confirm = true }, enabled = !job.cancelling) {
                Text(
                    when {
                        job.cancelling -> tr("멈추는 중", "Stopping")
                        job.done || job.failed -> tr("지우기", "Remove")
                        else -> tr("멈추기", "Stop")
                    },
                    fontSize = 13.sp, color = cs.onSurfaceVariant,
                )
            }
        }
    }
    if (confirm) {
        val finishedOrFailed = job.done || job.failed
        AlertDialog(
            onDismissRequest = { confirm = false },
            title = { Text(if (finishedOrFailed) tr("목록에서 지울까요?", "Remove from the list?") else tr("악보 만들기를 멈출까요?", "Stop making these scores?")) },
            text = {
                Text(
                    when {
                        job.failed -> tr("목록과 서버에서 지워져요. 다시 만들려면 새로 만들기에서 곡을 올려 주세요.", "It's removed here and on the server. To try again, start a new score.")
                        !job.done -> tr("지금까지 만든 내용은 사라져요.", "Progress so far will be lost.")
                        job.saved -> tr("보관함의 악보는 남아요.", "Saved scores stay in your library.")
                        else -> tr(
                            "저장하지 않은 악보라 서버의 파일도 지워지고 다시 볼 수 없어요.",
                            "Not saved, so the files on the server go too. You can't open it again.",
                        )
                    }
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    confirm = false
                    // 완성·실패한 카드는 목록에서 지운다 (저장하지 않은 결과는 서버 파일도). 만드는 중이면 서버 작업을 멈춘다.
                    ScoreJobs.cancel(ctx, job)
                }) {
                    Text(if (finishedOrFailed) tr("지우기", "Remove") else tr("멈추기", "Stop"), color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { confirm = false }) {
                    Text(if (finishedOrFailed) tr("닫기", "Close") else tr("계속 만들기", "Keep going"))
                }
            },
        )
    }
}

// ---------- 1-3. 보관함 ----------
@Composable
fun StorageTab(modifier: Modifier, onOpen: (Work) -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    var works by remember { mutableStateOf(WorkStore.load(ctx)) }
    var menuFor by remember { mutableStateOf<Work?>(null) }
    var renaming by remember { mutableStateOf<Work?>(null) }
    var deleting by remember { mutableStateOf<Work?>(null) }
    val bands = remember { Backend.bands(ctx) }
    val scope = androidx.compose.runtime.rememberCoroutineScope()

    // 지난번에 서버에 연결되지 않아 못 지운 악보가 있으면 다시 지운다.
    LaunchedEffect(Unit) {
        ServerCleanup.retryPending(ctx)
        RatingStore.sendPending(ctx)   // 인터넷이 안 돼서 못 보낸 별점도 다시 보낸다
    }

    Page(tr("보관함", "Library"), onBack = null, modifier = modifier) {
        if (works.isEmpty()) {
            Spacer(Modifier.height(80.dp))
            Text(
                tr("저장한 악보가 없어요.",
                    "No saved scores."),
                color = cs.onSurfaceVariant, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth(),
            )
        } else {
            InfoNote(tr("악보는 ROCKY 보관함에서 보고, 밴드에 공유해 멤버와 함께 봐요",
                "Scores stay in your ROCKY library. Share them with your band to view together"))
            Spacer(Modifier.height(12.dp))
            LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(works, key = { it.id }) { w ->
                    WorkRow(w, onClick = { onOpen(w) }) {
                        TextButton(onClick = { menuFor = w }) {
                            Text("⋮", fontSize = 20.sp, color = cs.onSurfaceVariant,
                                modifier = Modifier.semantics { contentDescription = tr("더보기", "More") })
                        }
                    }
                }
                item { Spacer(Modifier.height(12.dp)) }
            }
        }
    }

    menuFor?.let { w ->
        AlertDialog(
            onDismissRequest = { menuFor = null },
            title = { Text(w.title, maxLines = 2, overflow = TextOverflow.Ellipsis) },
            text = {
                Column {
                    TextButton(onClick = { menuFor = null; renaming = w }, modifier = Modifier.fillMaxWidth()) {
                        Text(tr("이름 바꾸기", "Rename"), modifier = Modifier.fillMaxWidth())
                    }
                    TextButton(onClick = { menuFor = null; deleting = w }, modifier = Modifier.fillMaxWidth()) {
                        Text(tr("보관함에서 삭제", "Delete from library"), color = cs.error, modifier = Modifier.fillMaxWidth())
                    }
                }
            },
            confirmButton = { TextButton(onClick = { menuFor = null }) { Text(tr("닫기", "Close")) } },
        )
    }
    renaming?.let { w ->
        TextInputDialog(
            title = tr("이름 바꾸기", "Rename"), initial = w.title, label = tr("악보 이름", "Score name"), maxLength = 60,
            onDismiss = { renaming = null },
            onConfirm = { t ->
                WorkStore.rename(ctx, w.id, t)
                // 내가 밴드에 공유한 같은 악보의 이름도 함께 바꾼다.
                AuthRepository.currentUserId(ctx)?.let { uid -> scope.launch { bands.renameMyWork(uid, w.id, t) } }
                works = WorkStore.load(ctx)
                renaming = null
                Toast.makeText(ctx, tr("이름을 바꿨어요", "Renamed"), Toast.LENGTH_SHORT).show()
            },
        )
    }
    deleting?.let { w ->
        val shared by androidx.compose.runtime.produceState<Boolean?>(null, w.id) {
            value = AuthRepository.currentUserId(ctx)?.let { uid -> bands.isShared(uid, w.id) } ?: false
        }
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text(tr("보관함에서 삭제할까요?", "Delete this score?")) },
            text = {
                Text(
                    when (shared) {
                        true -> tr("밴드에 공유한 악보라서 밴드에는 그대로 남아요.", "It's shared with a band, so the band keeps it.")
                        else -> tr(
                            "이 폰과 서버의 악보 파일이 함께 지워지고, 되돌릴 수 없어요.",
                            "The files on this phone and the server are deleted for good.",
                        )
                    }
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    WorkStore.remove(ctx, w.id)
                    // 만드는 중 목록에 남아 있으면 같이 빼고, 폰과 서버의 결과 파일을 지운다 (공유한 악보는 남긴다).
                    ScoreJobs.find(w.id)?.let { ScoreJobs.remove(it) }
                    ServerCleanup.deleteWork(ctx, w.id)
                    works = WorkStore.load(ctx); deleting = null
                }) {
                    Text(tr("삭제", "Delete"), color = cs.error)
                }
            },
            dismissButton = { TextButton(onClick = { deleting = null }) { Text(tr("취소", "Cancel")) } },
        )
    }
}

// ---------- 3. 곡 올리기 ----------
/** 고를 수 있는 곡 파일 (Req&Spec: MP3·WAV). 파일 앱에서 이 형식만 보이게 한다. */
private val PICK_TYPES = arrayOf("audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave")

/** 곡 이름 최대 글자 수 (보관함 이름 바꾸기와 같다). 일본어·한자·이모티콘도 한 글자로 센다. */
const val TITLE_MAX = 60

/** 곡 이름을 [TITLE_MAX]자까지 자른다. 글자(코드 포인트) 단위라 한자·이모티콘이 반으로 잘리지 않는다. */
fun limitTitle(s: String): String =
    if (s.codePointCount(0, s.length) <= TITLE_MAX) s else s.substring(0, s.offsetByCodePoints(0, TITLE_MAX))

/**
 * 2단계(마지막): 곡 파일을 고르고, 곡 이름을 확인한 뒤 바로 악보 만들기를 시작한다.
 * 원곡 악기는 묻지 않는다 (모델이 곡을 듣고 판단).
 * [redo]가 있으면 '기타 대수 바꿔서 다시 만들기': 같은 곡 파일을 다시 고르라고 안내하고 곡 이름을 채워 둔다.
 */
@Composable
fun UploadScreen(redo: GuitarRedo?, onBack: () -> Unit, onStart: (title: String, audio: AudioFile) -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    var picked by remember { mutableStateOf<String?>(null) }
    // 곡 이름. 파일 이름으로 채우고 사용자가 고칠 수 있다 (한국어·영어·일본어·중국어 등 어떤 글자든).
    var title by remember { mutableStateOf(redo?.title.orEmpty()) }
    // 고른 음원 파일.
    var audio by remember { mutableStateOf<AudioFile?>(null) }
    var editServer by remember { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri != null) {
            val name = fileName(ctx, uri)
            if (name.substringAfterLast('.').lowercase() !in listOf("mp3", "wav")) {
                Toast.makeText(ctx, tr("MP3나 WAV 파일만 고를 수 있어요", "Please pick an MP3 or WAV file"), Toast.LENGTH_LONG).show()
                return@rememberLauncherForActivityResult
            }
            // '다시 시도'에서 같은 파일을 다시 올릴 수 있게 읽기 권한을 계속 갖고 있는다.
            runCatching { ctx.contentResolver.takePersistableUriPermission(uri, android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION) }
            picked = displayName(ctx, uri)
            audio = AudioFile(uri, name)
            if (redo == null || title.isBlank()) title = limitTitle(picked.orEmpty().trim())
        }
    }
    val shape = RoundedCornerShape(24.dp)
    if (editServer) ServerDialog(onDismiss = { editServer = false })
    val ready = audio != null && title.isNotBlank()
    Page(tr("2 / 2단계", "Step 2 of 2"), onBack, actions = { StepBars(2) }, bottom = {
        Button(shape = ButtonShape,
            onClick = { val a = audio; if (a != null && title.isNotBlank()) onStart(title.trim(), a) }, enabled = ready,
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) {
            Text(
                when {
                    audio == null -> tr("곡을 먼저 골라주세요", "Pick a song first")
                    title.isBlank() -> tr("곡 이름을 적어 주세요", "Type the song name")
                    else -> tr("악보 만들기 시작", "Make my scores")
                },
                fontSize = 17.sp, fontWeight = FontWeight.Bold,
            )
        }
    }) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            if (redo != null) {
                InfoNote(guitarRedoNotice(redo), strong = true)
                Spacer(Modifier.height(6.dp))
                Text(
                    tr("서버에 곡 파일을 남기지 않아서, 같은 곡 파일을 한 번 더 골라 주세요. 처음부터 다시 만들어서 10분쯤 걸려요.",
                        "We don't keep song files on the server, so please pick the same file again. It starts over and takes about 10 min."),
                    fontSize = 13.sp, color = cs.onSurfaceVariant, lineHeight = 18.sp,
                )
                Spacer(Modifier.height(16.dp))
            }
            Text(tr("곡을 골라주세요", "Pick a song"), fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp)
            Spacer(Modifier.height(8.dp))
            Text(tr("MP3 · WAV 파일 · 원곡 악기는 ROCKY가 들어 보고 알아서 판단해요", "MP3 or WAV · ROCKY works out the song's instruments"), color = cs.onSurfaceVariant, lineHeight = 22.sp)
            Spacer(Modifier.height(20.dp))
            Column(
                Modifier.fillMaxWidth().height(170.dp)
                    .card(shape, cs)
                    .border(BorderStroke(2.dp, if (picked == null) cs.surfaceVariant else cs.primary), shape)
                    .clickable { launcher.launch(PICK_TYPES) }
                    .padding(20.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Text(if (picked == null) "＋" else "♪", fontSize = 44.sp, color = cs.primary)
                Spacer(Modifier.height(8.dp))
                Text(
                    picked ?: tr("파일 선택", "Choose a file"),
                    fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    color = if (picked == null) cs.onSurfaceVariant else cs.onSurface,
                )
                if (picked != null) Text(tr("눌러서 바꾸기", "Tap to change"), fontSize = 14.sp, color = cs.onSurface)
            }
            if (audio != null) {
                Spacer(Modifier.height(16.dp))
                OutlinedTextField(
                    value = title, onValueChange = { title = limitTitle(it) },
                    label = { Text(tr("곡 이름", "Song name")) },
                    singleLine = true,
                    supportingText = { Text(tr("보관함과 밴드에 이 이름으로 보여요 · 어떤 언어든 돼요", "Shown in your library and band · any language")) },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Spacer(Modifier.height(16.dp))
            // 밴드 곡이 아니어도 올릴 수는 있다. 결과가 좋지 않을 수 있다는 것만 미리 알린다.
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp))
                    .background(cs.secondary.copy(alpha = 0.14f)).padding(16.dp),
            ) {
                Text(tr("밴드 곡일수록 정확해요", "Band songs work best"), fontWeight = FontWeight.Bold, color = cs.secondary)
                Spacer(Modifier.height(4.dp))
                Text(
                    tr("오케스트라·독주·전자음악은 부정확할 수 있어요.",
                        "Orchestral, solo or electronic music may be less accurate."),
                    fontSize = 13.sp, color = cs.onSurfaceVariant, lineHeight = 19.sp,
                )
            }
            Spacer(Modifier.height(8.dp))
            // 시연·개발용 접속 설정. 일반 사용자에게는 눈에 띄지 않게 작게 둔다.
            TextButton(onClick = { editServer = true }, modifier = Modifier.padding(top = 4.dp)) {
                Text(tr("연결 설정", "Connection settings"), fontSize = 12.sp, color = cs.onSurfaceVariant, maxLines = 1)
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}

/** 접속 주소·키 바꾸기와 연결 확인 (시연·개발용). 기본값은 빌드 때 넣은 값(보통 http://localhost:8000). */
@Composable
fun ServerDialog(onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    var url by remember { mutableStateOf(ServerSettings.url(ctx)) }
    var key by remember { mutableStateOf(ServerSettings.key(ctx)) }
    var checking by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<String?>(null) }
    androidx.compose.runtime.LaunchedEffect(checking) {
        if (checking) {
            val ok = withContext(Dispatchers.IO) { RockyApi(url, key).health() }
            result = if (ok) tr("연결됨 ✓", "Connected ✓") else tr("연결할 수 없어요", "Can't connect")
            checking = false
        }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(tr("연결 설정", "Connection settings")) },
        text = {
            Column {
                OutlinedTextField(url, { url = it; result = null }, label = { Text(tr("주소", "Address")) }, singleLine = true)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(key, { key = it; result = null }, label = { Text(tr("키 (없으면 비워 두기)", "Key (leave empty if none)")) }, singleLine = true)
                Spacer(Modifier.height(4.dp))
                Text(tr("노트북에 USB로 연결했다면 http://localhost:8000", "Connected to a laptop by USB: http://localhost:8000"), fontSize = 12.sp)
                TextButton(onClick = { checking = true }, enabled = !checking && url.isNotBlank()) {
                    Text(if (checking) tr("확인 중…", "Checking…") else result ?: tr("연결 확인", "Test connection"))
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { ServerSettings.save(ctx, url, key); onDismiss() }) { Text(tr("저장", "Save")) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(tr("취소", "Cancel")) } },
    )
}
