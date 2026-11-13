package com.team3.rocky

import android.Manifest
import android.media.MediaPlayer
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.layout
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.team3.rocky.score.MeasureBox
import com.team3.rocky.score.MeasureClock
import com.team3.rocky.score.MeasureLayout
import com.team3.rocky.score.ScoreLayout
import com.team3.rocky.server.LocalScore
import com.team3.rocky.server.PdfPages
import com.team3.rocky.server.RockyApi
import com.team3.rocky.server.ScoreStore
import java.io.File
import kotlin.math.roundToInt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** "1:05"처럼 */
private fun mmss(ms: Int): String {
    val s = (ms / 1000).coerceAtLeast(0)
    return "${s / 60}:${(s % 60).toString().padStart(2, '0')}"
}

// ---------- 5. 결과 (악보 보기 + 듣기) ----------
@Composable
fun ResultScreen(
    work: Work,
    onBack: () -> Unit,
    onSaved: () -> Unit,
    onShareToBand: () -> Unit,
    /** '기타 대수 바꿔서 다시 만들기'에서 대수를 고르면 불린다 → 우리 밴드 구성·곡 올리기부터 다시. */
    onRedoGuitars: (GuitarRedo) -> Unit = {},
    myPart: String? = null,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    var saved by remember { mutableStateOf(WorkStore.load(ctx).any { it.id == work.id }) }
    val ai = work.aiGenerated
    // 서버에서 만들어 폰에 받아 둔 PDF·MIDI·MP3. 키를 바꾸면 새 결과로 바뀐다. 받아 둔 파일이 없으면 악보가 없다고 알려 준다.
    var local by remember(work.id) { mutableStateOf(ScoreStore.load(ctx, work.id)) }
    var changingKey by remember { mutableStateOf(false) }
    var keyDialog by remember { mutableStateOf(false) }
    var guitarDialog by remember { mutableStateOf(false) }
    if (guitarDialog) {
        GuitarCountDialog(
            heard = local?.result?.originalGuitars,
            // 모델이 찾은 원곡 악기 중 기타 아닌 것. 다시 만들 때 그대로 원곡 구성으로 보낸다.
            others = (local?.result?.originalParts ?: work.original).filter { it in Demo.NON_GUITAR }.distinct(),
            onDismiss = { guitarDialog = false },
            onNext = { plan -> guitarDialog = false; onRedoGuitars(plan.copy(title = work.title)) },
        )
    }
    // 대화상자에서 고른 키. '바꾸기'를 눌러야 서버가 한 번만 다시 만든다 (+반 키를 두 번 눌러도 한 번).
    var targetKey by remember(work.id) { mutableIntStateOf(local?.semitones ?: 0) }
    // 원곡에 있다고 골랐지만 원곡에서 소리가 거의 들리지 않은 파트. 칩을 누르면 무슨 뜻인지 3초 동안 보여준다.
    // 밴드에서 받은 악보는 서버 결과(faint_parts)로 판단한다.
    val warn = (work.unrecognized + local?.faint.orEmpty().filter { it in work.instruments && it !in ai }).toSet()
    var hint by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(hint) {
        if (hint != null) { kotlinx.coroutines.delay(3000); hint = null }
    }
    fun warnText(inst: String) = Demo.label(inst, work.instruments).let { name ->
        tr("⚠️ 원곡에서 $name 소리가 거의 들리지 않았어요", "⚠️ The $name is barely audible in the song")
    }
    // 서버 결과는 기타 2를 따로 가질 수 있어서 파트 이름 그대로 쓴다.
    fun baseOf(part: String?) = part ?: Demo.BAND
    fun serverPart(base: String) = base.takeIf { it != Demo.BAND }
    // 밴드에서 열면 내 파트를 먼저 골라 둔다. 보컬처럼 악보가 없는 파트는 밴드 전체 악보를 보여준다.
    val bandPart = myPart?.takeIf { it in work.instruments }
    var selectedPart by remember { mutableStateOf(bandPart) }   // null = 전체

    // ----- 재생 -----
    val player = remember { MediaPlayer() }
    var loadedBase by remember { mutableStateOf<String?>(null) }
    var playing by remember { mutableStateOf(false) }
    var position by remember { mutableIntStateOf(0) }
    var duration by remember { mutableIntStateOf(0) }
    var dragging by remember { mutableStateOf<Float?>(null) }
    var follow by remember { mutableStateOf(true) }
    DisposableEffect(Unit) { onDispose { player.release() } }

    // 개인 연습용의 '전체'는 올린 원곡 파일을 그대로 들려준다 (이 폰에 파일이 있고, 키를 바꾸지 않았을 때).
    // 원곡을 열 수 없으면 악보로 합성한 소리로 대신한다.
    var originalPlaying by remember { mutableStateOf(false) }
    fun originalSong(base: String): android.net.Uri? =
        work.audio?.takeIf { work.personal && base == Demo.BAND && (local?.semitones ?: 0) == 0 }?.let { android.net.Uri.parse(it) }

    /** 선택한 파트의 음원을 준비한다. 위치는 그대로 이어서 재생할 수 있게 [startAt]으로 옮긴다. */
    fun load(base: String, startAt: Int): Boolean {
        val song = originalSong(base)
        if (song != null) {
            val ok = runCatching {
                player.reset()
                player.setDataSource(ctx, song)
                player.prepare()
            }.isSuccess
            if (ok) {
                originalPlaying = true
                player.setOnCompletionListener { playing = false; position = 0; player.seekTo(0) }
                duration = player.duration
                player.seekTo(startAt.coerceIn(0, duration))
                position = startAt.coerceIn(0, duration)
                loadedBase = base
                return true
            }
        }
        originalPlaying = false
        // 서버 결과는 악보로 합성한 MP3(없으면 MIDI)를 들려준다.
        val path = local?.audio(serverPart(base))?.absolutePath
        if (path == null) {
            Toast.makeText(ctx, tr("이 파트는 소리가 없어요", "No audio for this part"), Toast.LENGTH_SHORT).show()
            return false
        }
        return try {
            player.reset()
            player.setDataSource(path)
            player.prepare()
            player.setOnCompletionListener { playing = false; position = 0; player.seekTo(0) }
            duration = player.duration
            player.seekTo(startAt.coerceIn(0, duration))
            position = startAt.coerceIn(0, duration)
            loadedBase = base
            true
        } catch (e: Exception) {
            Toast.makeText(ctx, tr("재생할 수 없어요", "Can't play this"), Toast.LENGTH_SHORT).show()
            loadedBase = null
            false
        }
    }

    val audioBase = baseOf(selectedPart)

    fun togglePlay() {
        if (playing) { player.pause(); playing = false; return }
        if (changingKey) return
        if (loadedBase != audioBase && !load(audioBase, position)) return
        player.start(); playing = true
    }

    fun selectPart(part: String?) {
        if (part == selectedPart) return
        selectedPart = part
        // 듣던 위치에서 새 파트로 이어서 재생한다.
        val wasPlaying = playing
        val newBase = baseOf(part)
        if (loadedBase != null && loadedBase != newBase) {
            if (load(newBase, position) && wasPlaying) player.start() else playing = false
        }
    }

    // 재생 중에는 위치를 자주 읽는다.
    LaunchedEffect(playing) {
        while (playing) {
            if (dragging == null) position = player.currentPosition
            delay(200)
        }
    }

    // ----- 악보 -----
    val scoreBase = baseOf(selectedPart)
    var pages by remember { mutableStateOf<List<ImageBitmap>?>(null) }
    // 마디 위치: 악보 그림에서 찾은 줄·마디선과, MIDI로 계산한 마디 시작 시간
    var measures by remember { mutableStateOf<MeasureLayout?>(null) }
    var clock by remember { mutableStateOf<MeasureClock?>(null) }
    val widthPx = with(LocalDensity.current) { LocalConfiguration.current.screenWidthDp.dp.roundToPx() }
    LaunchedEffect(scoreBase, local?.semitones) {
        pages = null
        measures = null
        // 키를 바꾸면 local이 새 결과로 바뀐다. 이번에 그릴 결과를 하나로 정해 둔다.
        val currentScore = local
        // 빈 여백을 잘라낸 그림으로 마디도 찾아서, 칠하는 위치와 그림이 맞게 한다.
        val bitmaps = withContext(Dispatchers.IO) {
            currentScore?.pdf(serverPart(scoreBase))
                ?.let { runCatching { PdfPages.render(it, widthPx) }.getOrNull() }
                .orEmpty().map { trimMargins(it) }
        }
        pages = bitmaps.map { it.asImageBitmap() }
        // 악보를 먼저 보여 주고, 마디 위치는 그 뒤에 찾는다 (페이지가 많으면 1–2초 걸린다).
        val c = withContext(Dispatchers.IO) {
            // 파트 MIDI가 없으면 밴드 전체 MIDI로 센다 (박자와 템포는 파트마다 같다).
            MeasureClock.fromFile(currentScore?.let { it.midi(serverPart(scoreBase)) ?: it.midi(null) })
        }
        clock = c
        if (c == null) return@LaunchedEffect
        measures = withContext(Dispatchers.Default) {
            runCatching {
                MeasureLayout.build(bitmaps.map { b ->
                    val px = IntArray(b.width * b.height).also { b.getPixels(it, 0, b.width, 0, 0, b.width, b.height) }
                    ScoreLayout.systems(px, b.width, b.height)
                }, c.count)
            }.getOrNull()?.takeIf { it.count > 0 }
        }
    }
    val scoreScroll = rememberScrollState()
    val currentMeasure = clock?.measureAt((dragging?.toLong() ?: position.toLong()))
    // 재생을 시작한 뒤에만 지금 마디를 칠한다.
    val currentBox = currentMeasure?.let { measures?.box(it) }?.takeIf { duration > 0 }
    // 마디를 못 찾은 악보(MIDI가 없거나 줄을 못 읽음)는 재생 시간 비율로 내린다. 마디를 찾았으면 ScoreSheet가 그 줄로 넘긴다.
    LaunchedEffect(position, follow, playing, scoreScroll.maxValue, measures) {
        if (measures == null && follow && playing && duration > 0 && scoreScroll.maxValue > 0) {
            val target = (scoreScroll.maxValue * position.toFloat() / duration).toInt()
            scoreScroll.animateScrollTo(target, tween(200, easing = LinearEasing))
        }
    }

    /** 키 바꾸기: 서버가 전체·악기별 악보와 음원을 새 키로 다시 만든다 (보관함에 저장한 악보만). */
    fun changeKey(next: Int) {
        if (changingKey || local == null) return
        changingKey = true
        scope.launch {
            try {
                val updated = withContext(Dispatchers.IO) {
                    if (next == 0) ScoreStore.useOriginal(ctx, work.id)
                    else ScoreStore.transpose(ctx, RockyApi.from(ctx), work.id, next)
                }
                player.reset()
                playing = false
                loadedBase = null
                position = 0
                duration = 0
                local = updated
                targetKey = updated.semitones
                keyDialog = false
            } catch (e: Exception) {
                Toast.makeText(
                    ctx, tr("키를 바꾸지 못했어요. 인터넷을 확인하고 다시 해 주세요.", "Couldn't change the key. Check the internet and try again."),
                    Toast.LENGTH_LONG,
                ).show()
            } finally {
                changingKey = false
            }
        }
    }

    // ----- 화면 상태 -----
    var menuOpen by remember { mutableStateOf(false) }
    var fullScreen by remember { mutableStateOf(false) }
    var zoom by remember { mutableFloatStateOf(1f) }
    // "악기를 누르면 그 악기만 들려요" 안내는 처음 한 번만. 닫으면 다시 보이지 않는다.
    val prefs = remember { ctx.getSharedPreferences(TIP_PREF, android.content.Context.MODE_PRIVATE) }
    var showTip by remember { mutableStateOf(!prefs.getBoolean(TIP_PARTS, false)) }
    fun closeTip() { showTip = false; prefs.edit().putBoolean(TIP_PARTS, true).apply() }
    BackHandler(enabled = fullScreen) { fullScreen = false }

    fun saveToLibrary() {
        WorkStore.add(ctx, work); saved = true; onSaved()
        Toast.makeText(ctx, tr("보관함에 저장했어요", "Saved"), Toast.LENGTH_SHORT).show()
    }

    // 기타가 맨 끝에 있으면 '그 밖의 것'으로 읽혀서, 다른 악기 사이에 둔다.
    val chipParts = work.instruments.sortedBy { RESULT_ORDER.indexOf(it).let { i -> if (i < 0) 99 else i } }

    val playerBar: @Composable (Boolean) -> Unit = { flat ->
        val who = selectedPart?.let { tr("${Demo.label(it, work.instruments)}만", "${Demo.label(it, work.instruments)} only") }
            ?: if (originalPlaying || (loadedBase == null && originalSong(Demo.BAND) != null)) tr("원곡", "Original song") else tr("밴드 전체", "Full band")
        // 몇 번째 마디인지 (MIDI로 셀 수 있을 때)
        val bar = clock?.let { c -> tr(" · ${(currentMeasure ?: 0) + 1}/${c.count}마디", " · bar ${(currentMeasure ?: 0) + 1}/${c.count}") }.orEmpty()
        val listening = who + bar
        Row(
            Modifier.fillMaxWidth()
                .then(if (flat) Modifier else Modifier.card(RoundedCornerShape(16.dp), cs))
                .padding(start = 8.dp, end = 14.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilledIconButton(onClick = { togglePlay() }, enabled = !changingKey, modifier = Modifier.size(48.dp), shape = CircleShape) {
                Text(
                    if (playing) "❚❚" else "▶", fontSize = 16.sp, fontWeight = FontWeight.Bold,
                    modifier = Modifier.semantics { contentDescription = if (playing) tr("일시정지", "Pause") else tr("재생", "Play") },
                )
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(listening, fontSize = 13.sp, fontWeight = FontWeight.Bold, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    Text(
                        "${mmss(dragging?.toInt() ?: position)} / ${if (duration > 0) mmss(duration) else "-:--"}",
                        fontSize = 12.sp, color = cs.onSurfaceVariant, maxLines = 1,
                    )
                }
                Slider(
                    value = (dragging ?: position.toFloat()).coerceIn(0f, duration.toFloat().coerceAtLeast(1f)),
                    valueRange = 0f..duration.toFloat().coerceAtLeast(1f),
                    enabled = duration > 0,
                    onValueChange = { dragging = it },
                    onValueChangeFinished = {
                        dragging?.let { player.seekTo(it.toInt()); position = it.toInt() }
                        dragging = null
                    },
                    colors = SliderDefaults.colors(inactiveTrackColor = cs.surfaceVariant),
                    modifier = Modifier.height(28.dp),
                )
            }
        }
    }

    // 악보 맨 아래 별점 (1~5). 품질 개선용으로 모은다.
    var stars by remember(work.id) { mutableStateOf(RatingStore.stars(ctx, work.id)) }

    // 결과를 처음 보고 나갈 때, 아직 별점을 안 매겼으면 평가 창을 한 번 띄운다 (팀이 피드백을 모으는 용도).
    var askRating by remember { mutableStateOf(false) }
    val wantRating = stars == 0 && local != null && !RatingStore.asked(ctx, work.id)
    fun leave() { if (wantRating) askRating = true else onBack() }
    BackHandler(enabled = wantRating && !fullScreen) { askRating = true }
    if (askRating) {
        RatingDialog(
            onSend = { n, note ->
                stars = n
                RatingStore.rate(ctx, work, n, note)
                RatingStore.markAsked(ctx, work.id)
                askRating = false
                onBack()
            },
            onLater = { RatingStore.markAsked(ctx, work.id); askRating = false; onBack() },
            onDismiss = { askRating = false },  // 창 밖을 누르면 악보로 돌아간다
        )
    }

    val sheet: @Composable (Modifier, Boolean) -> Unit = { modifier, bleed ->
        ScoreSheet(
            pages = pages, scroll = scoreScroll, zoom = zoom,
            onZoom = { z -> zoom = (zoom * z).coerceIn(1f, 4f) },
            fullScreen = fullScreen, onToggleFullScreen = { fullScreen = !fullScreen },
            hint = hint, onHintClick = { hint = null },
            bleed = bleed,
            box = currentBox,
            followBox = follow && playing,
            stars = stars,
            onRate = { n -> stars = n; RatingStore.rate(ctx, work, n) },
            modifier = modifier,
        )
    }

    if (fullScreen) {
        // 전체 화면: 악보와 재생 바만. 뒤로 가기나 오른쪽 아래 버튼으로 돌아온다.
        Column(Modifier.fillMaxSize().background(cs.background).statusBarsPadding()) {
            sheet(Modifier.fillMaxWidth().weight(1f).padding(horizontal = 8.dp, vertical = 8.dp), false)
            Box(
                Modifier.windowInsetsPadding(BottomSystemBars)
                    .padding(start = 12.dp, end = 12.dp, top = 4.dp, bottom = 16.dp),
            ) { playerBar(false) }
        }
        return
    }

    if (keyDialog) {
        val now = local?.semitones ?: 0
        AlertDialog(
            onDismissRequest = { if (!changingKey) { keyDialog = false; targetKey = now } },
            title = { Text(tr("키 바꾸기", "Change key")) },
            text = {
                Column {
                    Text(tr("지금: ${keyLabel(now)}", "Now: ${keyLabel(now)}"), color = cs.onSurfaceVariant)
                    Text(tr("바꿀 키: ${keyLabel(targetKey)}", "New key: ${keyLabel(targetKey)}"), fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(12.dp))
                    // 반 키 = 반음 1개, 한 키 = 반음 2개. 위아래 한 옥타브(12반음)까지.
                    for (row in listOf(listOf(-2, -1), listOf(1, 2))) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            row.forEach { step ->
                                OutlinedButton(
                                    shape = ButtonShape, onClick = { targetKey += step },
                                    enabled = !changingKey && targetKey + step in -12..12,
                                    modifier = Modifier.weight(1f), contentPadding = TightButtonPadding,
                                ) { Text(stepLabel(step), maxLines = 1) }
                            }
                        }
                        Spacer(Modifier.height(8.dp))
                    }
                    if (targetKey != 0) {
                        TextButton(onClick = { targetKey = 0 }, enabled = !changingKey) { Text(tr("원키로", "Original key")) }
                    }
                    if (changingKey) {
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 4.dp)) {
                            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.width(8.dp))
                            Text(tr("악보와 음원을 다시 만드는 중…", "Remaking scores and audio…"), fontSize = 13.sp)
                        }
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(
                        tr("낮은 줄을 더 낮추면 타브의 줄 튜닝도 바뀔 수 있어요.", "Lowering the lowest strings may change the TAB tuning."),
                        fontSize = 12.sp, color = cs.onSurfaceVariant,
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = { changeKey(targetKey) }, enabled = !changingKey && targetKey != now) {
                    Text(tr("${keyLabel(targetKey)}${if (targetKey == 0) "로" else "으로"} 바꾸기", "Change to ${keyLabel(targetKey)}"))
                }
            },
            dismissButton = {
                TextButton(onClick = { keyDialog = false; targetKey = now }, enabled = !changingKey) { Text(tr("닫기", "Close")) }
            },
        )
    }

    Page(work.title, { leave() }, actions = {
        Box {
            TextButton(onClick = { menuOpen = true }) {
                Text("⋮", fontSize = 22.sp, color = cs.onSurface,
                    modifier = Modifier.semantics { contentDescription = tr("메뉴", "Menu") })
            }
            DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                DropdownMenuItem(
                    text = { Text(if (saved) tr("보관함에 저장됨", "Saved") else tr("보관함에 저장", "Save to library")) },
                    enabled = !saved,
                    onClick = { menuOpen = false; saveToLibrary() },
                )
                // 개인 연습용 악보는 밴드에 공유하지 않는다.
                if (!work.personal) DropdownMenuItem(
                    text = { Text(tr("밴드에 공유", "Share with a band")) },
                    onClick = { menuOpen = false; onShareToBand() },
                )
                // 키 바꾸기는 서버에 남아 있는 결과로 다시 만들어서, 보관함에 저장한 악보만 된다.
                DropdownMenuItem(
                    text = {
                        Text(
                            if (saved) tr("키 바꾸기 · ${keyLabel(local?.semitones ?: 0)}", "Change key · ${keyLabel(local?.semitones ?: 0)}")
                            else tr("키 바꾸기 (저장 후)", "Change key (save first)"),
                        )
                    },
                    enabled = saved && local != null,
                    onClick = { menuOpen = false; keyDialog = true },
                )
                HorizontalDivider()
                DropdownMenuItem(
                    text = { Text(if (measures != null) tr("연주 중인 마디 따라가기", "Follow the playing bar") else tr("악보 자동 넘기기", "Auto-scroll")) },
                    trailingIcon = { Checkbox(checked = follow, onCheckedChange = null) },
                    onClick = { follow = !follow },
                )
                DropdownMenuItem(
                    text = { Text(tr("전체 화면", "Full screen")) },
                    onClick = { menuOpen = false; fullScreen = true },
                )
            }
        }
    }) {
        if (showTip) {
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(cs.surfaceVariant)
                    .padding(start = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(tr("악기를 누르면 그 악기만 들려요", "Tap an instrument to hear it alone"),
                    fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                TextButton(onClick = { closeTip() }) {
                    Text("✕", color = cs.onSurfaceVariant, modifier = Modifier.semantics { contentDescription = tr("닫기", "Close") })
                }
            }
            Spacer(Modifier.height(8.dp))
        }
        // 위: 악기 칩과 재생 바를 카드 하나로 묶는다.
        Column(Modifier.fillMaxWidth().card(RoundedCornerShape(16.dp), cs)) {
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())
                    .padding(start = 12.dp, end = 12.dp, top = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                PartChip(null, if (work.personal) tr("전체 · 원곡", "All · original") else tr("전체", "All"), selectedPart == null, ai = false) { selectPart(null) }
                chipParts.forEach { inst ->
                    val mark = when {
                        inst in warn -> "⚠️ "
                        inst in ai -> "✨ "
                        else -> ""
                    }
                    PartChip(inst, mark + Demo.label(inst, work.instruments), selectedPart == inst, ai = inst in ai, warn = inst in warn) {
                        selectPart(inst)
                        // 표시의 뜻은 칩을 누를 때만 잠깐 보여준다.
                        hint = when (inst) {
                            in warn -> warnText(inst)
                            in ai -> tr("✨ 원곡에 없어서 AI로 만든 파트예요", "✨ Not in the song, made with AI")
                            else -> null
                        }
                    }
                }
            }
            HorizontalDivider(color = cs.outlineVariant, modifier = Modifier.padding(top = 12.dp))
            Box(Modifier.padding(start = 2.dp, top = 4.dp, bottom = 4.dp)) { playerBar(true) }
        }
        // 원곡 기타 대수는 모델이 판단한다. 기타 파트가 이상해 보이면 대수를 직접 골라 처음부터 다시 만들 수 있다.
        if (Demo.guitarCount(work.instruments.toSet()) > 0) {
            // 한 줄짜리 눌리는 띠: 왼쪽 질문, 오른쪽 주황 동작. 줄 전체를 눌러도 된다.
            Row(
                Modifier.fillMaxWidth().padding(top = 8.dp).clip(RoundedCornerShape(12.dp))
                    .background(cs.surfaceVariant.copy(alpha = 0.6f))
                    .clickable { player.pause(); playing = false; guitarDialog = true }
                    .padding(horizontal = 12.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                InstrumentIcon("guitar", cs.onSurfaceVariant, size = 16.dp)
                Spacer(Modifier.width(8.dp))
                Text(
                    tr("기타 파트가 이상한가요?", "Guitar parts look off?"),
                    fontSize = 12.sp, color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                Text(tr("기타 대수 바꿔서 다시 만들기 ›", "Remake with a guitar count ›"), fontSize = 12.sp,
                    fontWeight = FontWeight.Bold, color = cs.primary, maxLines = 1)
            }
        }
        Text(
            tr("밴드 곡이 아니면 악보가 부정확할 수 있어요", "Less accurate for non-band songs"),
            fontSize = 11.sp, color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        )
        Spacer(Modifier.height(10.dp))
        // 아래: 악보. 화면 양옆 끝까지, 아래에서 올라온 종이처럼.
        sheet(Modifier.fillMaxWidth().weight(1f).bleed(20.dp), true)
    }
}

private const val TIP_PREF = "rocky_settings"
private const val TIP_PARTS = "tip_parts_seen"

/** 결과 화면 칩 순서. 기타를 가운데 두어 '기타(그 밖의 것)'로 읽히지 않게 한다. */
private val RESULT_ORDER = listOf("drums", "guitar", Demo.GUITAR2, "bass", "piano", Demo.VOCAL)

/** 지금 키: 원키 / +1반음 / −2반음 */
private fun keyLabel(semitones: Int): String = when {
    semitones == 0 -> tr("원키", "original")
    semitones > 0 -> tr("+${semitones}반음", "+$semitones semitones")
    else -> tr("−${-semitones}반음", "−${-semitones} semitones")
}

/** 키 바꾸기 버튼: 반 키(반음 1개), 한 키(반음 2개) */
private fun stepLabel(step: Int): String = when (step) {
    -2 -> tr("−한 키", "−1 tone")
    -1 -> tr("−반 키", "−½ tone")
    1 -> tr("+반 키", "+½ tone")
    else -> tr("+한 키", "+1 tone")
}

/**
 * 악보 영역. 두 손가락으로 벌리면 확대(최대 4배), 확대하면 위아래·옆으로 넘겨 본다.
 * [bleed]면 화면 양옆 끝까지 닿고 위 모서리만 둥근, 아래에서 올라온 종이 모양(결과 화면).
 * 오른쪽 위 버튼으로 전체 화면을 켜고 끄고, 아래 가운데에 몇 쪽인지 보여준다.
 */
@Composable
private fun ScoreSheet(
    pages: List<ImageBitmap>?,
    scroll: ScrollState,
    zoom: Float,
    onZoom: (Float) -> Unit,
    fullScreen: Boolean,
    onToggleFullScreen: () -> Unit,
    hint: String?,
    onHintClick: () -> Unit,
    bleed: Boolean,
    /** 지금 연주 중인 마디 (악보 그림의 픽셀 좌표). 칠하고, [followBox]면 그 줄로 넘긴다. */
    box: MeasureBox?,
    followBox: Boolean,
    stars: Int,
    onRate: (Int) -> Unit,
    modifier: Modifier,
) {
    val currentOnZoom by rememberUpdatedState(onZoom)
    val density = LocalDensity.current
    val hScroll = rememberScrollState()
    val chrome = Color(0xD918181B)
    BoxWithConstraints(
        modifier
            .clip(if (bleed) RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp) else RoundedCornerShape(16.dp))
            .background(Color.White)
            // 두 손가락일 때만 가로챈다. 한 손가락은 그대로 스크롤.
            .pointerInput(Unit) {
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
                    do {
                        val event = awaitPointerEvent(PointerEventPass.Initial)
                        if (event.changes.count { it.pressed } >= 2) {
                            val z = event.calculateZoom()
                            if (z != 1f) currentOnZoom(z)
                            event.changes.forEach { if (it.positionChanged()) it.consume() }
                        }
                    } while (event.changes.any { it.pressed })
                }
            },
        contentAlignment = Alignment.TopCenter,
    ) {
        val side = 14.dp
        val top = if (bleed) 24.dp else 12.dp
        val gap = 20.dp
        val pageWidth = (maxWidth - side * 2) * zoom
        val cardWidth = maxWidth - side * 2
        // 지금 마디가 있는 줄이 바뀔 때마다 그 줄이 위에 오게 넘긴다 (그림은 pageWidth에 맞춰 늘어난다).
        LaunchedEffect(box?.page, box?.top, followBox, pageWidth) {
            val b = box ?: return@LaunchedEffect
            val list = pages ?: return@LaunchedEffect
            if (!followBox || b.page !in list.indices) return@LaunchedEffect
            val (w, topPx, gapPx) = with(density) { Triple(pageWidth.toPx(), top.toPx(), gap.toPx()) }
            var y = topPx
            for (i in 0 until b.page) y += list[i].height * w / list[i].width + gapPx
            y += b.top * w / list[b.page].width
            scroll.animateScrollTo((y - with(density) { 28.dp.toPx() }).toInt().coerceAtLeast(0), tween(350))
        }
        when {
            pages == null -> CircularProgressIndicator(Modifier.padding(40.dp))
            pages.isEmpty() -> Text(
                tr("이 파트는 악보가 없어요", "No score for this part"),
                color = Color.Gray, textAlign = TextAlign.Center, maxLines = 1, modifier = Modifier.padding(40.dp),
            )
            else -> Column(
                Modifier.fillMaxSize().verticalScroll(scroll).horizontalScroll(hScroll)
                    .padding(start = side, end = side, top = top, bottom = 56.dp),
                verticalArrangement = Arrangement.spacedBy(gap),
            ) {
                val highlight = MaterialTheme.colorScheme.primary.copy(alpha = 0.16f)
                val edge = MaterialTheme.colorScheme.primary.copy(alpha = 0.7f)
                pages.forEachIndexed { i, bmp ->
                    val mine = box?.takeIf { it.page == i }
                    Image(
                        bitmap = bmp, contentDescription = tr("악보", "Score"),
                        contentScale = ContentScale.FillWidth,
                        modifier = Modifier.width(pageWidth).drawWithContent {
                            drawContent()
                            // 연주 중인 마디에 색을 칠하고 아래에 선을 긋는다.
                            if (mine != null) {
                                val k = size.width / bmp.width
                                val pad = 6f * k
                                val tl = Offset(mine.left * k, mine.top * k - pad * 2)
                                val sz = Size((mine.right - mine.left) * k, (mine.bottom - mine.top) * k + pad * 4)
                                drawRect(highlight, tl, sz)
                                drawRect(edge, Offset(tl.x, tl.y + sz.height - 3.dp.toPx()), Size(sz.width, 3.dp.toPx()))
                            }
                        },
                    )
                }
                // 악보를 끝까지 본 다음에 평가한다.
                RatingCard(stars, onRate, Modifier.width(cardWidth))
            }
        }
        // 위 가운데 손잡이 (종이 느낌)
        if (bleed) {
            Box(
                Modifier.align(Alignment.TopCenter).padding(top = 9.dp).size(width = 36.dp, height = 4.dp)
                    .clip(RoundedCornerShape(2.dp)).background(Color(0xFFD4D4D8)),
            )
        }
        // 몇 쪽인지: 스크롤 위치로 어림한다.
        if (!pages.isNullOrEmpty() && pages.size > 1) {
            val n = pages.size
            val page = if (scroll.maxValue <= 0) 1
            else (scroll.value.toFloat() / scroll.maxValue * (n - 1)).roundToInt() + 1
            Text(
                "$page / $n", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Color.White,
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 14.dp)
                    .clip(CircleShape).background(chrome).padding(horizontal = 12.dp, vertical = 6.dp),
            )
        }
        // 칩 표시(⚠️·✨)의 뜻. 악보 위에 3초 떠 있다가 사라진다 (눌러도 닫힘).
        if (hint != null) {
            Text(
                hint, fontSize = 13.sp, lineHeight = 18.sp, color = Color(0xFFF2F2F2), maxLines = 2,
                // 오른쪽 위 전체 화면 버튼과 겹치지 않게 비켜 둔다.
                modifier = Modifier.padding(start = 10.dp, end = 56.dp, top = if (bleed) 20.dp else 10.dp).fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color(0xF018181B))
                    .clickable(onClick = onHintClick)
                    .padding(horizontal = 14.dp, vertical = 10.dp),
            )
        }
        // 전체 화면 켜기/끄기 (오른쪽 위 작은 버튼, 누르는 영역은 44dp)
        Box(
            Modifier.align(Alignment.TopEnd).padding(top = 8.dp, end = 8.dp).size(44.dp)
                .clickable(onClick = onToggleFullScreen)
                .semantics { contentDescription = if (fullScreen) tr("전체 화면 닫기", "Exit full screen") else tr("전체 화면", "Full screen") },
            contentAlignment = Alignment.Center,
        ) {
            Box(
                Modifier.size(34.dp).clip(RoundedCornerShape(10.dp)).background(chrome),
                contentAlignment = Alignment.Center,
            ) { FullScreenGlyph(exit = fullScreen, color = Color.White) }
        }
    }
}

/**
 * 결과를 처음 보고 나갈 때 뜨는 평가 창: 별 5개로 총점(필수) + 한 줄 의견(선택).
 * '다음에'를 누르면 이 악보에서는 다시 묻지 않는다 (악보 맨 아래 별점 칸은 그대로 있음).
 */
@Composable
private fun RatingDialog(onSend: (Int, String) -> Unit, onLater: () -> Unit, onDismiss: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    var pick by remember { mutableIntStateOf(0) }
    var note by remember { mutableStateOf("") }
    val used = note.codePointCount(0, note.length)
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(tr("이 악보는 어땠나요?", "How was this score?")) },
        text = {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    tr("남겨 주신 평가는 ROCKY 악보를 더 좋게 만드는 데 써요.", "Your rating helps us make better scores."),
                    fontSize = 14.sp, color = cs.onSurfaceVariant, lineHeight = 20.sp,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                    for (n in 1..5) {
                        Box(
                            Modifier.size(48.dp).clip(CircleShape).clickable { pick = n }
                                .semantics { contentDescription = tr("별 ${n}개", "$n stars") },
                            contentAlignment = Alignment.Center,
                        ) {
                            Text("★", fontSize = 34.sp, color = if (n <= pick) cs.primary else cs.outlineVariant)
                        }
                    }
                }
                Text(
                    when (pick) {
                        0 -> tr("별을 눌러 5점 만점으로 골라 주세요", "Tap a star to rate out of 5")
                        1 -> tr("1점 · 별로예요", "1 · Poor")
                        2 -> tr("2점 · 아쉬워요", "2 · Fair")
                        3 -> tr("3점 · 보통이에요", "3 · Okay")
                        4 -> tr("4점 · 좋아요", "4 · Good")
                        else -> tr("5점 · 아주 좋아요", "5 · Great")
                    },
                    fontSize = 13.sp, maxLines = 1,
                    color = if (pick == 0) cs.onSurfaceVariant else cs.primary,
                    fontWeight = if (pick == 0) FontWeight.Normal else FontWeight.SemiBold,
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = note,
                    onValueChange = { v ->
                        val one = v.replace('\n', ' ')
                        note = if (one.codePointCount(0, one.length) <= RatingStore.COMMENT_MAX) one
                        else one.substring(0, one.offsetByCodePoints(0, RatingStore.COMMENT_MAX))
                    },
                    placeholder = { Text(tr("한 줄 의견 (선택)", "One-line comment (optional)")) },
                    singleLine = true,
                    supportingText = { Text("$used / ${RatingStore.COMMENT_MAX}") },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(enabled = pick > 0, onClick = { onSend(pick, note) }) { Text(tr("보내기", "Send")) }
        },
        dismissButton = { TextButton(onClick = onLater) { Text(tr("다음에", "Later")) } },
    )
}

/** 악보 맨 아래 별점 칸. 흰 종이 위에 놓이므로 밝은 색으로 그린다. */
@Composable
private fun RatingCard(stars: Int, onRate: (Int) -> Unit, modifier: Modifier) {
    val orange = MaterialTheme.colorScheme.primary
    Column(
        modifier.clip(RoundedCornerShape(16.dp)).background(Color(0xFFF4F4F5))
            .padding(horizontal = 16.dp, vertical = 18.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(tr("이 악보는 어땠나요?", "How was this score?"), fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Color(0xFF18181B))
        Spacer(Modifier.height(2.dp))
        Text(
            tr("별점은 악보를 더 정확하게 만드는 데 써요", "Your rating helps us make better scores"),
            fontSize = 12.sp, color = Color(0xFF71717A), maxLines = 1, overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.Center) {
            for (n in 1..5) {
                Box(
                    Modifier.size(48.dp).clip(CircleShape).clickable { onRate(n) }
                        .semantics { contentDescription = tr("별 ${n}개", "$n stars") },
                    contentAlignment = Alignment.Center,
                ) {
                    Text("★", fontSize = 32.sp, color = if (n <= stars) orange else Color(0xFFD4D4D8))
                }
            }
        }
        Text(
            if (stars == 0) tr("별을 눌러 5점 만점으로 평가해 주세요", "Tap a star to rate out of 5")
            else tr("${stars}점 · 고마워요! 다시 누르면 바꿀 수 있어요", "$stars / 5 · Thanks! Tap again to change"),
            fontSize = 12.sp, color = if (stars == 0) Color(0xFF71717A) else orange,
            fontWeight = if (stars == 0) FontWeight.Normal else FontWeight.SemiBold, maxLines = 1,
        )
    }
}

/** 부모의 좌우 여백([side])을 넘어 화면 양옆 끝까지 그린다. */
private fun Modifier.bleed(side: androidx.compose.ui.unit.Dp): Modifier = layout { measurable, constraints ->
    val extra = side.roundToPx() * 2
    val w = constraints.maxWidth + extra
    val placeable = measurable.measure(constraints.copy(minWidth = w, maxWidth = w))
    layout(constraints.maxWidth, placeable.height) { placeable.place(-extra / 2, 0) }
}

/**
 * 악보 그림의 위아래·양옆 빈 여백을 잘라낸다 (흰색이거나 투명한 칸은 여백으로 본다).
 * 여백이 크면 악보가 작고 휑해 보여서, 글자·음표가 있는 곳 둘레에 조금만 남긴다.
 */
internal fun trimMargins(src: android.graphics.Bitmap, pad: Int = 24): android.graphics.Bitmap {
    val w = src.width
    val h = src.height
    if (w < 4 || h < 4) return src
    val px = IntArray(w * h)
    src.getPixels(px, 0, w, 0, 0, w, h)
    var left = w; var right = -1; var topY = h; var bottom = -1
    for (y in 0 until h) {
        val row = y * w
        for (x in 0 until w) {
            val c = px[row + x]
            val a = c ushr 24
            if (a < 40) continue
            val lum = ((c shr 16 and 0xFF) * 3 + (c shr 8 and 0xFF) * 6 + (c and 0xFF)) / 10
            if (lum > 200) continue
            if (x < left) left = x
            if (x > right) right = x
            if (y < topY) topY = y
            if (y > bottom) bottom = y
        }
    }
    if (right < 0) return src
    val l = (left - pad).coerceAtLeast(0)
    val t = (topY - pad).coerceAtLeast(0)
    val r = (right + pad).coerceAtMost(w - 1)
    val b = (bottom + pad).coerceAtMost(h - 1)
    return android.graphics.Bitmap.createBitmap(src, l, t, r - l + 1, b - t + 1)
}

/** 네 모서리 꺾쇠. [exit]면 안쪽을 향한다. */
@Composable
private fun FullScreenGlyph(exit: Boolean, color: Color) {
    Canvas(Modifier.size(18.dp)) {
        val s = size.minDimension
        val a = s * 0.32f
        val w = s * 0.11f
        val stroke = Stroke(width = w, cap = StrokeCap.Round, join = StrokeJoin.Round)
        val o = w / 2
        // (모서리 점, 가로 방향, 세로 방향)
        listOf(
            Triple(Offset(o, o), 1f, 1f), Triple(Offset(s - o, o), -1f, 1f),
            Triple(Offset(o, s - o), 1f, -1f), Triple(Offset(s - o, s - o), -1f, -1f),
        ).forEach { (c, dx, dy) ->
            val corner = if (exit) Offset(c.x + dx * a, c.y + dy * a) else c
            val p = Path().apply {
                if (exit) {
                    moveTo(corner.x - dx * a, corner.y); lineTo(corner.x, corner.y); lineTo(corner.x, corner.y - dy * a)
                } else {
                    moveTo(corner.x + dx * a, corner.y); lineTo(corner.x, corner.y); lineTo(corner.x, corner.y + dy * a)
                }
            }
            drawPath(p, color, style = stroke)
        }
    }
}

/** 파트 고르기 칸. 악기 그림 + 이름 한 줄. [inst]가 null이면 '전체'. */
@Composable
private fun PartChip(
    inst: String?, text: String, selected: Boolean, ai: Boolean, warn: Boolean = false, onClick: () -> Unit,
) {
    val cs = MaterialTheme.colorScheme
    val fg = if (selected) cs.onPrimary else if (ai) cs.secondary else cs.onSurface
    Row(
        Modifier
            .card(
                CircleShape, cs,
                bg = when {
                    selected -> cs.primary
                    warn -> cs.error.copy(alpha = 0.16f)
                    ai -> cs.secondary.copy(alpha = 0.18f)
                    else -> cs.surface
                },
                line = if (selected) cs.primary else cs.outlineVariant,
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (inst != null) {
            InstrumentIcon(inst, fg, size = 18.dp)
            Spacer(Modifier.width(6.dp))
        }
        Text(text, fontWeight = FontWeight.Bold, color = fg, maxLines = 1)
    }
}

// ---------- 5-1. 기타 대수 바꿔서 다시 만들기 ----------
/**
 * 원곡에 기타가 몇 대인지(0~2) 고르는 창. 모델이 들은 대수([heard])를 함께 보여준다.
 * 고르면 [GuitarRedo]를 넘기고, 앱은 우리 밴드 구성·곡 올리기부터 다시 만든다.
 * [others]가 비어 있으면(모델이 기타 말고 아무것도 못 찾음) '없음'은 고를 수 없다: 원곡 구성이 비면 서버가 다시 '모름'으로 판단해서.
 */
@Composable
fun GuitarCountDialog(heard: Int?, others: List<String>, onDismiss: () -> Unit, onNext: (GuitarRedo) -> Unit) {
    val cs = MaterialTheme.colorScheme
    var pick by remember { mutableStateOf<Int?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(tr("원곡에 기타가 몇 대 있나요?", "How many guitars are in the song?")) },
        text = {
            Column {
                Text(
                    when (heard) {
                        null -> tr("기타 대수를 바꾸면 그 대수로 기타 파트를 다시 나눠요.", "We'll split the guitar parts again with your count.")
                        0 -> tr("지금 악보는 원곡에 기타가 없다고 보고 만들었어요.", "These scores assumed the song has no guitar.")
                        else -> tr("지금 악보는 원곡 기타를 ${heard}대로 보고 만들었어요.", "These scores assumed $heard guitar${if (heard > 1) "s" else ""} in the song.")
                    },
                    fontSize = 14.sp, lineHeight = 20.sp,
                )
                Spacer(Modifier.height(14.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(0, 1, 2).forEach { n ->
                        val on = pick == n
                        val enabled = n != heard && !(n == 0 && others.isEmpty())
                        val shape = RoundedCornerShape(14.dp)
                        Column(
                            Modifier.weight(1f).height(72.dp).clip(shape)
                                .background(if (on) cs.primary else cs.surfaceVariant.copy(alpha = if (enabled) 1f else 0.4f))
                                .clickable(enabled = enabled) { pick = n }
                                .semantics { contentDescription = tr("원곡 기타 ${n}대", "$n guitars in the song") },
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center,
                        ) {
                            Text(
                                when (n) { 0 -> tr("없음", "None"); 1 -> tr("1대", "1"); else -> tr("2대", "2") },
                                fontSize = 18.sp, fontWeight = FontWeight.Bold,
                                color = when { on -> cs.onPrimary; enabled -> cs.onSurface; else -> cs.onSurfaceVariant.copy(alpha = 0.5f) },
                            )
                            if (n == heard) Text(tr("지금", "Now"), fontSize = 11.sp, color = cs.onSurfaceVariant)
                        }
                    }
                }
                Spacer(Modifier.height(14.dp))
                Text(
                    tr(
                        "고른 대수로 처음부터 다시 만들어요 (10분쯤). ROCKY는 올린 곡 파일을 보관하지 않아서, 악기를 확인하고 같은 곡 파일을 한 번 더 올려 주세요. 지금 악보는 그대로 남아요.",
                        "It starts over with your count (about 10 min). We don't keep song files, so check your band and pick the same file again. These scores stay.",
                    ),
                    fontSize = 13.sp, color = cs.onSurfaceVariant, lineHeight = 18.sp,
                )
            }
        },
        confirmButton = {
            TextButton(enabled = pick != null, onClick = {
                val n = pick ?: return@TextButton
                onNext(GuitarRedo(title = "", guitars = n, original = Demo.redoOriginal(others, n)))
            }) { Text(tr("다음", "Next")) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(tr("취소", "Cancel")) } },
    )
}
