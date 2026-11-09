@file:OptIn(ExperimentalMaterial3Api::class)

package com.team3.rocky

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
import com.team3.rocky.band.LocalBandRepository
import com.team3.rocky.band.PickScoreScreen
import com.team3.rocky.band.ShareToBandScreen
import com.team3.rocky.progress.AudioFile
import com.team3.rocky.progress.ScoreJob
import com.team3.rocky.progress.ScoreJobs
import com.team3.rocky.progress.Stage
import com.team3.rocky.progress.formatEta
import com.team3.rocky.server.RockyApi
import com.team3.rocky.server.ServerSettings
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// ---------- 화면 목록 ----------
sealed class Screen {
    object Login : Screen()                                       // 0. 로그인
    object SignUp : Screen()                                      // 0-1. 회원가입
    object Account : Screen()                                     // 0-2. 내 정보
    object Main : Screen()                                        // 1. 하단 탭 (새 악보 / 진행상황 / 보관함 / 나의 밴드)
    object Lineup : Screen()                                      // 2. 우리 밴드 구성
    object Upload : Screen()                                      // 3. 음원 업로드
    class Original(val title: String, val audio: AudioFile?) : Screen() // 3-1. 원곡 밴드 구성 (audio null = 데모 곡)
    // 5. 결과. 밴드에서 열면 myPart(이 밴드에서 내 파트) 악보를 먼저 보여준다.
    class Result(val work: Work, val myPart: String? = null, val jobId: Long? = null) : Screen()
    class Export(val work: Work) : Screen()                       // 6. 내보내기
    object BandJoin : Screen()                                    // 7-1. 밴드 만들기·참여
    class BandDetail(val bandId: Long) : Screen()                 // 7-2. 밴드 상세
    class ShareToBand(val work: Work) : Screen()                  // 7-3. 결과 → 밴드에 공유
    class PickScore(val bandId: Long) : Screen()                  // 7-4. 밴드 → 보관함 악보 공유
}

enum class Tab(private val ko: String, private val en: String) {
    NEW("홈", "Home"), PROGRESS("만드는 중", "In progress"), STORAGE("보관함", "Library"), BANDS("내 밴드", "Bands");

    val label get() = tr(ko, en)
}

@Composable
fun RockyApp() {
    val ctx = LocalContext.current
    val auth = remember { AuthRepository(ctx) }
    val bands: BandRepository = remember { LocalBandRepository(ctx) }
    // 앱을 켤 때 로그인 상태가 남아 있으면 바로 홈, 아니면 로그인 화면에서 시작한다.
    var user by remember { mutableStateOf(auth.currentUser()) }
    val stack = remember { mutableStateListOf(if (user != null) Screen.Main else Screen.Login) }
    var tab by remember { mutableStateOf(Tab.NEW) }
    var lineup by remember { mutableStateOf(setOf<String>()) }
    var original by remember { mutableStateOf(setOf<String>()) }
    // 원곡 구성을 '모르겠어요'로 고른 경우. ROCKY가 원곡을 듣고 판단한다.
    var originalUnknown by remember { mutableStateOf(false) }
    // 프로필 사진을 바꾸면 숫자를 올려서 다시 읽게 한다.
    var photoVersion by remember { mutableIntStateOf(0) }
    val appScope = androidx.compose.runtime.rememberCoroutineScope()

    fun go(s: Screen) { stack.add(s) }
    fun back() { if (stack.size > 1) stack.removeAt(stack.lastIndex) }
    // 로그인·로그아웃 뒤에는 이전 화면으로 돌아갈 수 없게 쌓인 화면을 비운다.
    fun restart(s: Screen) { stack.clear(); stack.add(s) }
    fun signedIn(u: User) { user = u; tab = Tab.NEW; restart(Screen.Main) }
    fun newScore(preset: Set<String>) { lineup = preset; go(Screen.Lineup) }
    fun openTab(t: Tab) { tab = t; restart(Screen.Main) }

    // 탭 화면에서 뒤로가기를 누르면 먼저 '새 악보' 탭으로 돌아간다.
    BackHandler(enabled = stack.size > 1 || (stack.last() == Screen.Main && tab != Tab.NEW)) {
        if (stack.size > 1) back() else tab = Tab.NEW
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
                    onLogout = { auth.logout(); ScoreJobs.clear(); user = null; restart(Screen.Login) },
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
            Screen.Lineup -> LineupScreen(
                title = tr("새 악보", "New score"),
                heading = tr("우리 밴드 악기", "Your band"),
                sub = tr(
                    "연주할 악기를 모두 고르세요.\n곡에 없는 파트는 새로 만들어요.",
                    "Pick every instrument you play.\nParts not in the song are added.",
                ),
                selected = lineup,
                onToggle = { i -> lineup = Demo.toggleLineup(lineup, i) },
                onGuitars = { n -> lineup = Demo.setGuitarCount(lineup, n) },
                onBack = { back() },
                nextLabel = tr("다음 · 악기 ${lineup.size}개", "Next · ${lineup.size} instruments"),
                onNext = { go(Screen.Upload) },
            )
            Screen.Upload -> UploadScreen(
                onBack = { back() },
                onNext = { title, audio ->
                    // 데모 곡은 원곡 구성을 미리 채워 둔다.
                    original = if (audio == null) Demo.DEMO_ORIGINAL.toSet() else emptySet()
                    originalUnknown = false
                    go(Screen.Original(title, audio))
                },
            )
            is Screen.Original -> {
              // 파이프라인 규칙: 원곡에 기타가 없으면 기타는 1대까지만 새로 만들 수 있다.
              val twoGuitarsFromNone = !originalUnknown && original.isNotEmpty() &&
                  Demo.guitarCount(original) == 0 && Demo.guitarCount(lineup) == 2
              OriginalScreen(
                songTitle = s.title,
                songSub = s.audio?.fileName ?: tr("데모 곡", "Demo song"),
                selected = original,
                onToggle = { i -> original = Demo.toggleLineup(original, i); originalUnknown = false },
                onGuitars = { n -> original = Demo.setGuitarCount(original, n); originalUnknown = false },
                onBack = { back() },
                canNext = (original.isNotEmpty() || originalUnknown) && !twoGuitarsFromNone,
                unknown = originalUnknown,
                onUnknown = { originalUnknown = !originalUnknown; if (originalUnknown) original = emptySet() },
                footer = {
                    val ai = Demo.ordered(Demo.aiGenerated(Demo.ordered(lineup), Demo.ordered(original)))
                    when {
                        twoGuitarsFromNone -> InfoNote(
                            tr(
                                "곡에 기타가 없으면 기타는 1대까지만 돼요. 우리 밴드 기타를 1대로 바꿔 주세요.",
                                "With no guitar in the song, only 1 guitar can be added.",
                            ),
                            strong = true,
                        )
                        originalUnknown -> Unit   // 밑줄 글자에 이미 "곡을 분석해 찾아요"가 있다
                        original.isNotEmpty() -> InfoNote(
                            if (ai.isEmpty()) tr("곡 그대로 악보로 옮겨요", "Scored as in the song")
                            else tr("새로 만들 파트: ", "Will add: ") +
                                ai.joinToString(" · ") { Demo.label(it, lineup) },
                            strong = ai.isNotEmpty(),
                        )
                    }
                },
                onNext = {
                    ScoreJobs.start(
                        ctx, s.title, Demo.ordered(lineup),
                        if (originalUnknown) emptyList() else Demo.ordered(original),
                        audio = s.audio,
                    )
                    openTab(Tab.PROGRESS)
                },
              )
            }
            is Screen.Result -> ResultScreen(
                work = s.work,
                myPart = s.myPart,
                onBack = { back() },
                onSaved = { s.jobId?.let { ScoreJobs.find(it) }?.saved = true },
                onExport = { go(Screen.Export(s.work)) },
                onShareToBand = { go(Screen.ShareToBand(s.work)) },
            )
            is Screen.Export -> ExportScreen(work = s.work, onBack = { back() })

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
                    onOpenScore = { work, part -> go(Screen.Result(work, myPart = part)) },
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
            Tab.NEW -> HomeTab(user, photoVersion, inner, onAccount, onNew, onProgress = { onTab(Tab.PROGRESS) })
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
@Composable
fun HomeTab(
    user: User,
    photoVersion: Int,
    modifier: Modifier,
    onAccount: () -> Unit,
    onNew: () -> Unit,
    onProgress: () -> Unit,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val photo = remember(photoVersion, user.id) { ProfileStore.load(ctx, user.id) }
    val running = ScoreJobs.runningCount
    val finished = ScoreJobs.jobs.count { it.done && !it.saved }

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
        Spacer(Modifier.height(16.dp))
        Text("ROCKY", fontSize = 48.sp, fontWeight = FontWeight.Black, color = cs.primary)
        Text(tr("어떤 곡이든, 우리 밴드 악보로", "Any song, scored for your band"), fontSize = 16.sp, color = cs.onSurfaceVariant)
        Spacer(Modifier.height(28.dp))
        BigCard(
            tr("새 악보 만들기", "Make a new score"),
            tr("곡을 올리면 파트별 악보가 나와요", "Upload a song, get every part"),
            cs.primary, cs.onPrimary, onNew,
        )

        if (running > 0 || finished > 0) {
            Spacer(Modifier.height(12.dp))
            BigCard(
                if (running > 0) tr("${running}곡 만드는 중", "Making $running ${plural(running, "song", "songs")}")
                else tr("완성된 악보 ${finished}곡", "$finished ${plural(finished, "score", "scores")} ready"),
                if (running > 0) tr("눌러서 얼마나 남았는지 보기", "Tap to see how long is left")
                else tr("눌러서 바로 열어 보기", "Tap to open"),
                cs.surfaceVariant, cs.onSurface, onProgress,
            )
        }

        // 처음 쓰는 사람이 무엇을 하면 되는지 바로 알 수 있게 세 단계로 보여준다.
        Spacer(Modifier.height(32.dp))
        Text(tr("이렇게 만들어요", "How it works"), fontWeight = FontWeight.Bold, fontSize = 17.sp)
        Spacer(Modifier.height(10.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HowStep("1", tr("악기 고르기", "Pick instruments"), Modifier.weight(1f))
            HowStep("2", tr("곡 올리기", "Upload a song"), Modifier.weight(1f))
            HowStep("3", tr("악보 받기", "Get scores"), Modifier.weight(1f))
        }

        // 결과가 잘 나오는 곡을 고르는 요령. 옆으로 넘겨 본다.
        Spacer(Modifier.height(28.dp))
        Text(tr("정확도 팁", "Tips"), fontWeight = FontWeight.Bold, fontSize = 17.sp)
        Spacer(Modifier.height(10.dp))
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            TipCard("drums", tr("밴드 곡일수록 정확해요", "Band songs work best"),
                tr("드럼·베이스·기타·피아노 편성", "Drums, bass, guitar, keys"))
            TipCard("guitar", tr("곡의 악기를 골라 주세요", "Pick the song's instruments"),
                tr("고르면 더 정확해져요", "It improves accuracy"))
            TipCard("piano", tr("MP3 · WAV만 가능", "MP3 or WAV only"),
                tr("음질이 좋을수록 정확해요", "Better audio, better notes"))
            TipCard("vocal", tr("라이브·커버도 돼요", "Live and covers work"),
                tr("관객 소리가 크면 덜 정확해요", "Loud crowds lower accuracy"))
        }
        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun HowStep(no: String, text: String, modifier: Modifier) {
    val cs = MaterialTheme.colorScheme
    Column(
        modifier.clip(RoundedCornerShape(16.dp)).background(cs.surface).padding(vertical = 14.dp, horizontal = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier.size(28.dp).clip(androidx.compose.foundation.shape.CircleShape).background(cs.primary.copy(alpha = 0.16f)),
            contentAlignment = Alignment.Center,
        ) { Text(no, fontWeight = FontWeight.Bold, color = cs.primary, fontSize = 14.sp) }
        Spacer(Modifier.height(8.dp))
        Text(text, fontSize = 13.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun TipCard(icon: String, title: String, body: String) {
    val cs = MaterialTheme.colorScheme
    Column(
        Modifier.width(210.dp).clip(RoundedCornerShape(18.dp)).background(cs.surface).padding(16.dp),
    ) {
        InstrumentIcon(icon, cs.primary, size = 26.dp)
        Spacer(Modifier.height(10.dp))
        Text(title, fontWeight = FontWeight.Bold, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.height(4.dp))
        Text(body, fontSize = 13.sp, lineHeight = 18.sp, color = cs.onSurfaceVariant, maxLines = 2)
    }
}

@Composable
fun BigCard(title: String, sub: String, bg: Color, fg: Color, onClick: () -> Unit) {
    Column(
        Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(bg)
            .clickable(onClick = onClick)
            .padding(24.dp)
    ) {
        Text(title, fontSize = 24.sp, fontWeight = FontWeight.Bold, color = fg)
        Spacer(Modifier.height(6.dp))
        Text(sub, fontSize = 14.sp, color = fg.copy(alpha = 0.8f), lineHeight = 20.sp)
    }
}

@Composable
fun WorkRow(w: Work, onClick: () -> Unit, trailing: @Composable RowScope.() -> Unit = {}) {
    val cs = MaterialTheme.colorScheme
    Row(
        Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(cs.surface)
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
            OutlinedButton(onClick = onNew, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                Text(tr("새 악보 만들기", "Make a new score"))
            }
        } else {
            InfoNote(tr("앱을 닫지 않으면 계속 만들어요",
                "Keeps going unless you close the app"))
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
            .clip(RoundedCornerShape(18.dp))
            .background(cs.surface)
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
        if (err != null) {
            Text(tr("악보를 만들지 못했어요", "Couldn't make the scores"), fontWeight = FontWeight.Bold, color = cs.error, fontSize = 14.sp)
            Text(err, fontSize = 13.sp, color = cs.onSurface, lineHeight = 18.sp)
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { ScoreJobs.retry(ctx, job) }, modifier = Modifier.weight(1f).height(44.dp), contentPadding = TightButtonPadding) {
                    Text(tr("다시 시도", "Retry"), fontSize = 14.sp, maxLines = 1)
                }
                OutlinedButton(onClick = { ScoreJobs.useDemo(ctx, job) }, modifier = Modifier.weight(1f).height(44.dp), contentPadding = TightButtonPadding) {
                    Text(tr("예시 결과 보기", "See a sample"), fontSize = 14.sp, maxLines = 1)
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
            TextButton(onClick = { confirm = true }) {
                Text(if (job.done || job.failed) tr("지우기", "Remove") else tr("멈추기", "Stop"), fontSize = 13.sp, color = cs.onSurfaceVariant)
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
                        job.failed -> tr("다시 만들려면 곡을 다시 올려 주세요.", "Upload the song again to retry.")
                        !job.done -> tr("지금까지 만든 내용은 사라져요.", "Progress so far will be lost.")
                        job.saved -> tr("보관함의 악보는 남아요.", "Saved scores stay in your library.")
                        else -> tr("저장하지 않아서 다시 볼 수 없어요.", "Not saved. You can't open it again.")
                    }
                )
            },
            confirmButton = {
                TextButton(onClick = { confirm = false; ScoreJobs.remove(job) }) {
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
    val bands = remember { LocalBandRepository(ctx) }
    val scope = androidx.compose.runtime.rememberCoroutineScope()

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
            InfoNote(tr("악보를 열고 ⋮ › 내보내기로 휴대폰에 저장해요",
                "Open a score, then ⋮ › Export to save it"))
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
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text(tr("보관함에서 삭제할까요?", "Delete this score?")) },
            text = { Text(tr("밴드에 공유한 악보는 남아요.", "Copies shared with bands stay.")) },
            confirmButton = {
                TextButton(onClick = { WorkStore.remove(ctx, w.id); works = WorkStore.load(ctx); deleting = null }) {
                    Text(tr("삭제", "Delete"), color = cs.error)
                }
            },
            dismissButton = { TextButton(onClick = { deleting = null }) { Text(tr("취소", "Cancel")) } },
        )
    }
}

// ---------- 2. 밴드 구성 (우리 밴드 / 원곡) ----------
@Composable
fun LineupScreen(
    title: String,
    heading: String,
    sub: String,
    selected: Set<String>,
    onToggle: (String) -> Unit,
    onGuitars: (Int) -> Unit,
    onBack: () -> Unit,
    nextLabel: String,
    onNext: () -> Unit,
    canNext: Boolean = selected.isNotEmpty(),
    /** null이면 '모르겠어요' 칸을 보여주지 않는다. */
    unknown: Boolean? = null,
    onUnknown: () -> Unit = {},
    footer: @Composable () -> Unit = {},
) {
    val cs = MaterialTheme.colorScheme
    Page(title, onBack, bottom = {
        Button(
            onClick = onNext, enabled = canNext,
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) { Text(nextLabel, fontSize = 17.sp) }
    }) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            Text(heading, fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp)
            Spacer(Modifier.height(8.dp))
            Text(sub, color = cs.onSurfaceVariant, lineHeight = 22.sp)
            Spacer(Modifier.height(24.dp))
            Demo.INSTRUMENTS.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { inst ->
                        val count = if (inst == "guitar") Demo.guitarCount(selected) else if (inst in selected) 1 else 0
                        InstrumentTile(
                            inst, count, Modifier.weight(1f),
                            onCount = if (inst == "guitar") onGuitars else null,
                        ) { onToggle(inst) }
                    }
                }
                Spacer(Modifier.height(12.dp))
            }
            if (unknown != null) {
                val shape = RoundedCornerShape(20.dp)
                Box(
                    Modifier.fillMaxWidth().height(60.dp)
                        .clip(shape)
                        .background(if (unknown) cs.primary else cs.surface)
                        .border(BorderStroke(2.dp, if (unknown) cs.primary else cs.surfaceVariant), shape)
                        .clickable(onClick = onUnknown),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(tr("잘 모르겠어요", "I'm not sure"), fontSize = 18.sp, fontWeight = FontWeight.Bold,
                        color = if (unknown) cs.onPrimary else cs.onSurface)
                }
                Spacer(Modifier.height(12.dp))
            }
            footer()
            Spacer(Modifier.height(16.dp))
        }
    }
}

/**
 * 악기 칸. 누르면 켜고 끈다.
 * [onCount]가 있으면(기타) 켜졌을 때 이름 아래에 − 1대 + 버튼이 나와서 대수를 바꿀 수 있다.
 * 작은 폰에서도 잘리지 않게 이름과 대수 버튼을 다른 줄에 둔다.
 * [onBg]·[onFg]는 켜졌을 때 색. 우리 밴드는 주황, 원곡 화면은 흰색(무채색)으로 구분한다.
 */
@Composable
fun InstrumentTile(
    inst: String,
    count: Int,
    modifier: Modifier,
    onCount: ((Int) -> Unit)? = null,
    onBg: Color = MaterialTheme.colorScheme.primary,
    onFg: Color = MaterialTheme.colorScheme.onPrimary,
    onClick: () -> Unit,
) {
    val cs = MaterialTheme.colorScheme
    val on = count > 0
    val shape = RoundedCornerShape(20.dp)
    val fg = if (on) onFg else cs.onSurface
    Column(
        modifier.height(140.dp)
            .clip(shape)
            .background(if (on) onBg else cs.surface)
            .border(BorderStroke(2.dp, if (on) onBg else cs.surfaceVariant), shape)
            .clickable(onClick = onClick)
            .padding(14.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
            InstrumentIcon(inst, fg, size = 36.dp)
            Spacer(Modifier.weight(1f))
            if (onCount != null && !on) Text(tr("1~2대", "1–2"), fontSize = 13.sp, color = cs.onSurfaceVariant, maxLines = 1)
        }
        Column {
            Text(Demo.kor(inst), fontSize = 18.sp, fontWeight = FontWeight.Bold, color = fg, maxLines = 1)
            if (onCount != null && on) {
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    StepButton("−", enabled = count > 1, bg = onFg, fg = onBg) { onCount(count - 1) }
                    Text(tr("${count}대", "×$count"), fontSize = 15.sp, maxLines = 1, fontWeight = FontWeight.Bold, color = fg,
                        modifier = Modifier.padding(horizontal = 8.dp))
                    StepButton("+", enabled = count < 2, bg = onFg, fg = onBg) { onCount(count + 1) }
                }
            }
        }
    }
}

@Composable
private fun StepButton(text: String, enabled: Boolean, bg: Color, fg: Color, onClick: () -> Unit) {
    Box(
        Modifier.size(32.dp)
            .clip(androidx.compose.foundation.shape.CircleShape)
            .background(bg.copy(alpha = if (enabled) 1f else 0.35f))
            .clickable(enabled = enabled, onClick = onClick)
            .semantics { contentDescription = if (text == "+") tr("기타 늘리기", "More guitars") else tr("기타 줄이기", "Fewer guitars") },
        contentAlignment = Alignment.Center,
    ) {
        Text(text, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = fg)
    }
}

// ---------- 2-1. 원곡 악기 (곡을 올린 다음) ----------
/**
 * 원곡에 나오는 악기를 고르는 화면. 우리 밴드 화면과 헷갈리지 않게
 * 맨 위에 올린 곡을 보여 주고, 선택 색을 주황 대신 흰색(무채색)으로 쓴다.
 */
@Composable
fun OriginalScreen(
    songTitle: String,
    songSub: String,
    selected: Set<String>,
    unknown: Boolean,
    onToggle: (String) -> Unit,
    onGuitars: (Int) -> Unit,
    onUnknown: () -> Unit,
    onBack: () -> Unit,
    canNext: Boolean,
    onNext: () -> Unit,
    footer: @Composable () -> Unit,
) {
    val cs = MaterialTheme.colorScheme
    Page(tr("3 / 3단계", "Step 3 of 3"), onBack, actions = {
        Row(Modifier.padding(end = 16.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            repeat(3) { Box(Modifier.width(22.dp).height(4.dp).clip(RoundedCornerShape(2.dp)).background(cs.onSurface)) }
        }
    }, bottom = {
        Button(
            onClick = onNext, enabled = canNext,
            colors = ButtonDefaults.buttonColors(containerColor = cs.onSurface, contentColor = cs.surface),
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) { Text(tr("악보 만들기 시작", "Make my scores"), fontSize = 17.sp, fontWeight = FontWeight.Bold) }
    }) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            // 올린 곡
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(cs.surface).padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    Modifier.size(52.dp).clip(androidx.compose.foundation.shape.CircleShape).background(cs.surfaceVariant),
                    contentAlignment = Alignment.Center,
                ) {
                    Box(
                        Modifier.size(38.dp).border(1.dp, cs.onSurfaceVariant, androidx.compose.foundation.shape.CircleShape),
                        contentAlignment = Alignment.Center,
                    ) { Box(Modifier.size(12.dp).clip(androidx.compose.foundation.shape.CircleShape).background(cs.onSurface)) }
                }
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text(tr("올린 곡", "Your song"), fontSize = 12.sp, color = cs.onSurfaceVariant)
                    Text(songTitle, fontSize = 17.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(songSub, fontSize = 12.sp, color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Spacer(Modifier.height(22.dp))
            Text(tr("이 곡에서는\n어떤 악기가 들리나요?", "Which instruments\ndo you hear?"),
                fontSize = 26.sp, fontWeight = FontWeight.Bold, lineHeight = 34.sp)
            Spacer(Modifier.height(6.dp))
            Text(tr("우리 밴드 말고, 곡에 나오는 악기만 골라주세요", "Not your band, only what plays in the song"),
                color = cs.onSurfaceVariant, fontSize = 14.sp)
            Spacer(Modifier.height(18.dp))
            Demo.INSTRUMENTS.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { inst ->
                        val count = if (inst == "guitar") Demo.guitarCount(selected) else if (inst in selected) 1 else 0
                        InstrumentTile(
                            inst, count, Modifier.weight(1f),
                            onCount = if (inst == "guitar") onGuitars else null,
                            onBg = cs.onSurface, onFg = cs.surface,
                        ) { onToggle(inst) }
                    }
                }
                Spacer(Modifier.height(12.dp))
            }
            // '잘 모르겠어요'는 밑줄 글자로. 고르면 위의 악기 선택이 비워진다.
            TextButton(onClick = onUnknown, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                Text(
                    if (unknown) tr("✓ 잘 모르겠어요 (곡을 분석해 찾아요)", "✓ Not sure (we'll detect them)")
                    else tr("잘 모르겠어요, 곡을 분석해 주세요", "Not sure, detect them for me"),
                    color = cs.onSurface, fontSize = 15.sp,
                    fontWeight = if (unknown) FontWeight.Bold else FontWeight.Normal,
                    textDecoration = TextDecoration.Underline,
                )
            }
            Spacer(Modifier.height(4.dp))
            footer()
            Spacer(Modifier.height(16.dp))
        }
    }
}

// ---------- 3. 곡 올리기 ----------
/** 고를 수 있는 곡 파일 (Req&Spec: MP3·WAV). 파일 앱에서 이 형식만 보이게 한다. */
private val PICK_TYPES = arrayOf("audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave")

@Composable
fun UploadScreen(onBack: () -> Unit, onNext: (title: String, audio: AudioFile?) -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    var picked by remember { mutableStateOf<String?>(null) }
    // 고른 음원 파일. 데모 곡이면 null.
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
        }
    }
    val shape = RoundedCornerShape(24.dp)
    if (editServer) ServerDialog(onDismiss = { editServer = false })
    Page(tr("곡 올리기", "Upload a song"), onBack, bottom = {
        Button(
            onClick = { picked?.let { onNext(it, audio) } }, enabled = picked != null,
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) { Text(if (picked == null) tr("곡을 먼저 골라주세요", "Pick a song first") else tr("다음", "Next"), fontSize = 17.sp) }
    }) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            Text(tr("곡을 골라주세요", "Pick a song"), fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp)
            Spacer(Modifier.height(8.dp))
            Text(tr("MP3 · WAV 파일", "MP3 or WAV file"), color = cs.onSurfaceVariant)
            Spacer(Modifier.height(20.dp))
            Column(
                Modifier.fillMaxWidth().height(170.dp)
                    .clip(shape)
                    .background(cs.surface)
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
            Spacer(Modifier.height(16.dp))
            OutlinedButton(
                onClick = { picked = Demo.SONG_TITLE; audio = null },
                modifier = Modifier.fillMaxWidth().height(50.dp),
            ) {
                Text(tr("데모 곡으로 체험", "Try the demo song"))
            }
            Spacer(Modifier.height(12.dp))
            Text(
                tr("몇 분 걸려요. 데모 곡은 바로 나와요.",
                    "Takes a few minutes. The demo is instant."),
                fontSize = 13.sp, color = cs.onSurfaceVariant, lineHeight = 19.sp,
            )
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
