package com.team3.rocky

import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.OutlinedTextField
import kotlin.math.roundToInt
import androidx.compose.ui.layout.layout
import android.Manifest
import android.media.MediaPlayer
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.foundation.gestures.drag
import androidx.compose.foundation.gestures.awaitLongPressOrCancellation
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.TextButton
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import com.team3.rocky.server.LocalScore
import com.team3.rocky.server.ScoreStore
import com.team3.rocky.server.RockyApi
import com.team3.rocky.score.MeasureBox
import com.team3.rocky.score.MeasureClock
import com.team3.rocky.score.MeasureLayout
import com.team3.rocky.score.PrintedMeasures
import com.team3.rocky.score.ScoreLayout
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Size
import java.io.File

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
    myPart: String? = null,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val saved = remember { WorkStore.load(ctx).any { it.id == work.id } }
    val ai = work.aiGenerated
    // 서버에서 만들어 폰에 받아 둔 PDF·MIDI·MP3. 키를 바꾸면 새 결과로 바뀐다. 받아 둔 파일이 없으면 악보가 없다고 알려 준다.
    var local by remember(work.id) { mutableStateOf(ScoreStore.load(ctx, work.id)) }
    var changingKey by remember { mutableStateOf(false) }
    var keyDialog by remember { mutableStateOf(false) }
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
    // 밴드에서 열면 내 파트, 개인 연습용이면 연습할 악기를 먼저 골라 둔다 ('내 파트' 글자 대신 칩이 켜져 있다).
    // 보컬처럼 악보가 없는 파트는 밴드 전체 악보를 보여준다.
    val bandPart = myPart?.takeIf { it in work.instruments }
        ?: work.instruments.firstOrNull()?.takeIf { work.personal }
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

    /** 선택한 파트의 음원을 준비한다. 위치는 그대로 이어서 재생할 수 있게 [startAt]으로 옮긴다. */
    fun load(base: String, startAt: Int): Boolean {
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
        // 새 악보의 첫 쪽이 나올 때까지는 보던 악보를 그대로 둔다 (빈 화면이 깜빡이지 않게). 칠하기만 지운다.
        measures = null
        // 키를 바꾸면 local이 새 결과로 바뀐다. 이번에 그릴 결과를 하나로 정해 둔다.
        val currentScore = local
        val pdf = currentScore?.pdf(serverPart(scoreBase))
        // 빈 여백을 잘라낸 그림으로 마디도 찾아서, 칠하는 위치와 그림이 맞게 한다.
        // 한 번 그린 악보는 기억해 두고, 처음 그릴 때는 한 쪽씩 그리면서 바로 보여 준다.
        val loaded: ScorePages = if (pdf == null) ScorePages.EMPTY else {
            val key = ScorePageCache.key(pdf, widthPx)
            ScorePageCache.get(key) ?: try {
                renderScorePages(pdf, widthPx) { partial ->
                    withContext(Dispatchers.Main) { pages = partial.images }
                }.also { ScorePageCache.put(key, it) }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                ScorePages.EMPTY
            }
        }
        pages = loaded.images
        val rendered = loaded.widths
        val crops = loaded.crops
        val bitmaps = loaded.bitmaps
        // 악보를 먼저 보여 주고, 마디 위치는 그 뒤에 찾는다 (페이지가 많으면 1–2초 걸린다).
        val c = withContext(Dispatchers.IO) {
            // 파트 MIDI가 없으면 밴드 전체 MIDI로 센다 (박자와 템포는 파트마다 같다).
            MeasureClock.fromFile(currentScore?.let { it.midi(serverPart(scoreBase)) ?: it.midi(null) })
        }
        clock = c
        if (c == null) return@LaunchedEffect
        // 서버가 적어 둔 마디 위치가 있으면 그대로 쓴다. 악보와 MIDI는 둘 다 0번 박에서 시작하므로
        // 마디 수가 같거나, 악보 끝에 빈 마디가 하나 더 있을 때만 믿는다. 다르면 그림에서 찾는다.
        val printed = withContext(Dispatchers.IO) {
            currentScore?.measures(serverPart(scoreBase))?.let { f -> runCatching { PrintedMeasures.parse(f.readText()) }.getOrNull() }
        }?.takeIf { it.count == c.count || it.count == c.count + 1 }
        if (printed != null) {
            measures = printed.layout(rendered, crops)
                .takeIf { it.count > 0 }
            if (measures != null) return@LaunchedEffect
        }
        measures = withContext(Dispatchers.Default) {
            runCatching {
                MeasureLayout.build(bitmaps.map { b ->
                    val px = IntArray(b.width * b.height).also { b.getPixels(it, 0, b.width, 0, 0, b.width, b.height) }
                    ScoreLayout.systems(px, b.width, b.height)
                }, c.count)
            }.getOrNull()?.takeIf { it.count > 0 }
        }
    }
    val currentMeasure = clock?.measureAt((dragging?.toLong() ?: position.toLong()))
    // 재생을 시작한 뒤에만 지금 마디를 칠한다.
    val currentBox = currentMeasure?.let { measures?.box(it) }?.takeIf { duration > 0 }
    // 마디를 못 찾은 악보(MIDI가 없거나 줄을 못 읽음)는 재생 시간 비율로 쪽을 넘긴다. 마디를 찾았으면 ScoreSheet가 그 쪽·줄로 넘긴다.
    val followPage = pages?.size?.takeIf { measures == null && follow && playing && duration > 0 && it > 0 }
        ?.let { n -> (n * position.toFloat() / duration).toInt().coerceIn(0, n - 1) }

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
    // 처음 열면 이 화면에서 할 수 있는 것을 안내한다 (홈의 처음 안내와 같은 모양). 메뉴에서 다시 볼 수 있다.
    var guide by remember { mutableStateOf(!ResultGuide.seen(ctx)) }
    if (guide) ResultGuideDialog(personal = work.personal, onDone = { guide = false })
    BackHandler(enabled = fullScreen) { fullScreen = false }


    val playerBar: @Composable (Boolean) -> Unit = { flat ->
        val who = selectedPart?.let { tr("${Demo.label(it, work.instruments)}만", "${Demo.label(it, work.instruments)} only") }
            ?: tr("밴드 전체", "Full band")
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

    // 악보 마지막 장 다음의 별점 (1~5). 품질 개선용으로 모은다.
    // '제출' 전에는 별을 계속 바꿀 수 있고 별점 장도 계속 남는다. 제출하면 같은 장에 의견 칸(선택)이 나오고,
    // 의견도 '제출'하면 별점 장이 더 이상 나오지 않는다.
    var submitted by remember(work.id) { mutableStateOf(RatingStore.stars(ctx, work.id) > 0) }
    var finished by remember(work.id) { mutableStateOf(RatingStore.finished(ctx, work.id)) }
    var stars by remember(work.id) { mutableIntStateOf(0) }
    var comment by remember(work.id) { mutableStateOf("") }
    val ratingPage: (@Composable () -> Unit)? = if (finished) null else {
        {
            if (!submitted) RatingCard(stars, onRate = { stars = it }, onSubmit = {
                if (stars > 0) { RatingStore.rate(ctx, work, stars); submitted = true }
            }, modifier = Modifier.fillMaxWidth())
            else CommentCard(comment, onChange = { comment = it.take(1000) }, onSubmit = {
                RatingStore.comment(ctx, work, comment); finished = true
                Toast.makeText(ctx, tr("고마워요! ROCKY가 더 좋아지는 데 쓸게요", "Thanks! It helps ROCKY get better"), Toast.LENGTH_SHORT).show()
            }, modifier = Modifier.fillMaxWidth())
        }
    }

    val sheet: @Composable (Modifier, Boolean) -> Unit = { modifier, bleed ->
        ScoreSheet(
            pages = pages, followPage = followPage, zoom = zoom,
            onZoom = { z -> zoom = (zoom * z).coerceIn(1f, 4f) },
            fullScreen = fullScreen, onToggleFullScreen = { fullScreen = !fullScreen },
            hint = hint, onHintClick = { hint = null },
            bleed = bleed,
            box = currentBox,
            followBox = follow && playing,
            ratingPage = ratingPage,
            modifier = modifier,
        )
    }

    if (fullScreen) {
        // 전체 화면: 악보와 재생 바만. 재생 바는 보통 화면과 같은 자리(아래)에 같은 모양으로 둔다.
        Column(Modifier.fillMaxSize().background(cs.background).statusBarsPadding()) {
            sheet(Modifier.fillMaxWidth().weight(1f).padding(horizontal = 8.dp, vertical = 8.dp), false)
            Box(
                Modifier.windowInsetsPadding(BottomSystemBars)
                    .padding(start = 20.dp, end = 20.dp, top = 4.dp, bottom = 20.dp),
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

    // 위: 악기 고르기 · 가운데: 악보(좌우로 넘김, 마지막 장 다음은 별점) · 아래: 재생 바 (전체 화면과 같은 자리)
    Page(work.title, onBack, bottom = { playerBar(false) }, actions = {
        Box {
            TextButton(onClick = { menuOpen = true }) {
                Text("⋮", fontSize = 22.sp, color = cs.onSurface,
                    modifier = Modifier.semantics { contentDescription = tr("메뉴", "Menu") })
            }
            DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                // 완성된 악보는 보관함에 자동으로 저장되므로 '보관함에 저장'은 없다.
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
                            else tr("키 바꾸기 (보관함 악보만)", "Change key (library scores only)"),
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
                DropdownMenuItem(
                    text = { Text(tr("사용법 보기", "How to use")) },
                    onClick = { menuOpen = false; guide = true },
                )
            }
        }
    }) {
        // 위: 악기 고르기. 네 악기 자리는 늘 같고, 이 곡에 없는 악기는 회색으로 막아 둔다.
        // 개인 연습용은 고를 것이 없어서 칸을 두지 않는다 (기타 2대일 때만 기타 1·기타 2).
        val onSelect: (String?) -> Unit = { inst ->
            selectPart(inst)
            // 표시의 뜻은 칩을 누를 때만 잠깐 보여준다.
            hint = when (inst) {
                null -> null
                in warn -> warnText(inst)
                in ai -> tr("✨ 원곡에 없어서 AI로 만든 파트예요", "✨ Not in the song, made with AI")
                else -> null
            }
        }
        if (!work.personal) {
            PartGrid(
                instruments = work.instruments, selected = selectedPart,
                mark = { inst -> when { inst in warn -> "⚠️ "; inst in ai -> "✨ "; else -> "" } },
                ai = ai.toSet(), warn = warn, onSelect = onSelect,
            )
        } else if (Demo.GUITAR2 in work.instruments) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("guitar", Demo.GUITAR2).forEach { inst ->
                    PartChip(
                        inst, (if (inst in ai) "✨ " else "") + Demo.label(inst, work.instruments), selectedPart == inst,
                        ai = inst in ai, modifier = Modifier.weight(1f),
                    ) { onSelect(inst) }
                }
            }
        }
        // 개인 연습용 악기가 원곡에 없어서 AI로 만든 악보면 알려 준다 (2차 UAT). 원곡에서 옮긴 악보는 표시 없음.
        if (work.personal && Demo.GUITAR2 !in work.instruments && work.instruments.any { it in ai }) {
            Text(
                tr("✨ 원곡에 없는 악기라 AI가 만든 악보예요", "✨ Not in the song, so this score was made with AI"),
                fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = cs.primary,
                textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().testTag("solo_ai"),
            )
        }
        // 원곡에 기타가 없다고 들었는데 기타 2대를 골랐으면 기타는 1대만 새로 만든다 (재생성 기능을 뺀 대신).
        if (local?.oneGuitarOnly == true) {
            InfoNote(
                tr("원곡에 기타가 없어서 기타 파트는 1개만 새로 만들었어요", "The song has no guitar, so only one guitar part was made"),
                modifier = Modifier.padding(top = 8.dp),
            )
        }
        Text(
            tr("밴드 곡이 아니면 악보가 부정확할 수 있어요", "Less accurate for non-band songs"),
            fontSize = 12.sp, color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        )
        Spacer(Modifier.height(8.dp))
        // 가운데: 악보. 아래 재생 바와 겹치지 않게 남은 높이를 다 쓴다.
        sheet(Modifier.fillMaxWidth().weight(1f), false)
    }
}



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
 * 악보 영역. 한 쪽씩 좌우로 넘기고, 마지막 쪽 다음 장이 별점이다.
 * 두 손가락으로 벌리면 확대(최대 4배), 확대하면 그 쪽 안에서 위아래·옆으로 움직인다(확대 중에는 쪽을 넘기지 않음).
 * 오른쪽 위 버튼으로 전체 화면을 켜고 끄고, 아래 가운데에 몇 쪽인지 보여준다.
 */
@Composable
private fun ScoreSheet(
    pages: List<ImageBitmap>?,
    /** 마디를 못 찾은 악보에서 재생 위치로 어림한 쪽. 있으면 그 쪽으로 넘긴다. */
    followPage: Int?,
    zoom: Float,
    onZoom: (Float) -> Unit,
    fullScreen: Boolean,
    onToggleFullScreen: () -> Unit,
    hint: String?,
    onHintClick: () -> Unit,
    bleed: Boolean,
    /** 지금 연주 중인 마디 (악보 그림의 픽셀 좌표). 칠하고, [followBox]면 그 쪽·줄로 넘긴다. */
    box: MeasureBox?,
    followBox: Boolean,
    /** 마지막 악보 쪽 다음 장(별점·의견). null이면 다 끝내서 보여주지 않는다. */
    ratingPage: (@Composable () -> Unit)?,
    modifier: Modifier,
) {
    val currentOnZoom by rememberUpdatedState(onZoom)
    val density = LocalDensity.current
    val chrome = Color(0xD918181B)
    val scoreCount = pages?.size ?: 0
    // 악보 쪽 수 + 별점 한 장 (제출 전까지)
    val rating = ratingPage != null
    val pager = rememberPagerState { scoreCount + if (rating) 1 else 0 }
    // 제출해서 별점 장이 없어지면 마지막 악보 쪽으로 돌아간다.
    LaunchedEffect(rating) { if (!rating && scoreCount > 0 && pager.currentPage >= scoreCount) pager.scrollToPage(scoreCount - 1) }
    // 쪽마다 위아래 위치 (확대했거나 쪽이 화면보다 길 때)
    val scrolls = remember(pages) { List(scoreCount) { ScrollState(0) } }
    // 파트를 바꾸면 첫 쪽부터
    LaunchedEffect(pages) { if (scoreCount > 0) pager.scrollToPage(0) }
    BoxWithConstraints(
        modifier
            .clip(if (bleed) RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp) else RoundedCornerShape(16.dp))
            .background(Color.White)
            // 두 손가락일 때만 가로챈다. 한 손가락은 그대로 넘기기·스크롤.
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
        val side = 12.dp
        val top = if (bleed) 24.dp else 12.dp
        val pageWidth = (maxWidth - side * 2) * zoom
        // 지금 마디가 있는 쪽으로 넘기고, 그 쪽 안에서 그 줄이 위에 오게 한다 (그림은 pageWidth에 맞춰 늘어난다).
        LaunchedEffect(box?.page, box?.top, followBox, pageWidth, pages) {
            val b = box ?: return@LaunchedEffect
            val list = pages ?: return@LaunchedEffect
            if (!followBox || b.page !in list.indices) return@LaunchedEffect
            if (pager.currentPage != b.page) pager.animateScrollToPage(b.page)
            val (w, topPx) = with(density) { pageWidth.toPx() to top.toPx() }
            val y = topPx + b.top * w / list[b.page].width
            scrolls[b.page].animateScrollTo((y - with(density) { 28.dp.toPx() }).toInt().coerceAtLeast(0), tween(350))
        }
        LaunchedEffect(followPage) {
            val target = followPage ?: return@LaunchedEffect
            if (target != pager.currentPage) pager.animateScrollToPage(target)
        }
        when {
            pages == null -> CircularProgressIndicator(Modifier.padding(40.dp))
            pages.isEmpty() -> Text(
                tr("이 파트는 악보가 없어요", "No score for this part"),
                color = Color.Gray, textAlign = TextAlign.Center, maxLines = 1, modifier = Modifier.padding(40.dp),
            )
            else -> HorizontalPager(
                state = pager, modifier = Modifier.fillMaxSize(),
                // 확대 중에는 손가락으로 그 쪽 안을 움직이고, 쪽은 넘기지 않는다.
                userScrollEnabled = zoom <= 1.01f,
            ) { i ->
                if (i >= pages.size) {
                    // 마지막 장: 악보를 다 본 다음 평가한다.
                    Box(Modifier.fillMaxSize().padding(horizontal = side), contentAlignment = Alignment.Center) {
                        ratingPage?.invoke()
                    }
                    return@HorizontalPager
                }
                val bmp = pages[i]
                val mine = box?.takeIf { it.page == i }
                val highlight = MaterialTheme.colorScheme.primary.copy(alpha = 0.16f)
                val edge = MaterialTheme.colorScheme.primary.copy(alpha = 0.7f)
                Box(
                    Modifier.fillMaxSize().verticalScroll(scrolls[i])
                        .then(if (zoom > 1.01f) Modifier.horizontalScroll(rememberScrollState()) else Modifier)
                        .padding(start = side, end = side, top = top, bottom = 56.dp),
                ) {
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
            }
        }
        // 위 가운데 손잡이 (종이 느낌)
        if (bleed) {
            Box(
                Modifier.align(Alignment.TopCenter).padding(top = 9.dp).size(width = 36.dp, height = 4.dp)
                    .clip(RoundedCornerShape(2.dp)).background(Color(0xFFD4D4D8)),
            )
        }
        // 몇 쪽인지. 마지막 악보 쪽에서는 다음 장이 별점이라고 알려 준다.
        // 긴 악보를 쉽게 넘기도록 (2차 UAT): 누르면 쪽 번호를 입력해 바로 가고,
        // 꾹 누른 채 옆으로 밀면 쪽이 빠르게 넘어간다 (손가락을 떼면 그 쪽에 머문다).
        if (!pages.isNullOrEmpty()) {
            val n = pages.size
            val cur = pager.currentPage
            val label = when {
                cur >= n -> tr("★ 별점", "★ Rate")
                cur == n - 1 && rating -> tr("$n / $n · 넘기면 별점 ›", "$n / $n · swipe to rate ›")
                else -> "${cur + 1} / $n"
            }
            val scope = rememberCoroutineScope()
            var askPage by remember { mutableStateOf(false) }
            var scrubbing by remember { mutableStateOf<Int?>(null) }
            val stepPx = with(density) { 22.dp.toPx() }
            Text(
                label, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Color.White,
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 10.dp)
                    .clip(CircleShape).background(chrome)
                    .semantics { contentDescription = tr("쪽 이동: 누르면 쪽 번호 입력, 꾹 누르고 옆으로 밀면 빠르게 넘기기", "Go to page: tap to type a page, hold and slide to flip") }
                    .pointerInput(n) {
                        awaitEachGesture {
                            val down = awaitFirstDown()
                            val long = awaitLongPressOrCancellation(down.id)
                            if (long == null) {
                                // 꾹 누르기 전에 뗐으면 누른 것: 쪽 번호 입력
                                if (currentEvent.changes.none { it.pressed } && currentEvent.changes.none { it.isConsumed }) askPage = true
                                return@awaitEachGesture
                            }
                            val start = pager.currentPage.coerceAtMost(n - 1)
                            var dx = 0f
                            scrubbing = start
                            drag(long.id) { change ->
                                dx += change.positionChange().x
                                change.consume()
                                val target = (start + (dx / stepPx).toInt()).coerceIn(0, n - 1)
                                if (target != scrubbing) {
                                    scrubbing = target
                                    scope.launch { pager.scrollToPage(target) }
                                }
                            }
                            scrubbing = null
                        }
                    }
                    .padding(horizontal = 16.dp, vertical = 9.dp),
            )
            // 꾹 눌러 넘기는 동안 가운데에 크게 몇 쪽인지 보여 준다.
            scrubbing?.let { pg ->
                Column(
                    Modifier.align(Alignment.Center).clip(RoundedCornerShape(18.dp)).background(chrome)
                        .padding(horizontal = 28.dp, vertical = 16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("${pg + 1} / $n", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Color.White)
                    Text(tr("옆으로 밀어서 넘기기", "Slide to flip"), fontSize = 12.sp, color = Color(0xFFD4D4D8))
                }
            }
            if (askPage) PageJumpDialog(
                count = n, current = cur.coerceAtMost(n - 1) + 1,
                onDismiss = { askPage = false },
                onGo = { page -> askPage = false; scope.launch { pager.scrollToPage(page - 1) } },
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

/** 쪽 번호를 입력해서 그 쪽으로 가는 창. */
@Composable
private fun PageJumpDialog(count: Int, current: Int, onDismiss: () -> Unit, onGo: (Int) -> Unit) {
    var text by remember { mutableStateOf("") }
    val page = text.toIntOrNull()
    val ok = page != null && page in 1..count
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(tr("몇 쪽으로 갈까요?", "Go to page")) },
        text = {
            OutlinedTextField(
                value = text,
                onValueChange = { v -> text = v.filter { it.isDigit() }.take(4) },
                label = { Text(tr("1~$count 쪽 (지금 $current 쪽)", "1–$count (now $current)")) },
                singleLine = true,
                isError = text.isNotEmpty() && !ok,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Go),
                keyboardActions = KeyboardActions(onGo = { if (ok) onGo(page!!) }),
                modifier = Modifier.testTag("page_jump"),
            )
        },
        confirmButton = { TextButton(onClick = { onGo(page!!) }, enabled = ok) { Text(tr("이동", "Go")) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(tr("취소", "Cancel")) } },
    )
}

/** 악보 마지막 장 다음의 별점 칸. 흰 종이 위에 놓이므로 밝은 색으로 그린다. */
@Composable
private fun RatingCard(stars: Int, onRate: (Int) -> Unit, onSubmit: () -> Unit, modifier: Modifier) {
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
            else tr("${stars}점 · 제출하기 전에는 다시 눌러 바꿀 수 있어요", "$stars / 5 · Tap again to change before sending"),
            fontSize = 12.sp, color = if (stars == 0) Color(0xFF71717A) else orange,
            fontWeight = if (stars == 0) FontWeight.Normal else FontWeight.SemiBold,
        )
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = onSubmit, enabled = stars > 0, shape = ButtonShape,
            modifier = Modifier.fillMaxWidth().height(48.dp).testTag("rating_submit"),
        ) { Text(tr("제출", "Send"), fontWeight = FontWeight.Bold) }
    }
}

/** 별점을 제출한 뒤 같은 장에 나오는 의견 칸 (선택). 비워 두고 제출해도 된다. */
@Composable
private fun CommentCard(text: String, onChange: (String) -> Unit, onSubmit: () -> Unit, modifier: Modifier) {
    val dark = Color(0xFF18181B)
    Column(
        modifier.clip(RoundedCornerShape(16.dp)).background(Color(0xFFF4F4F5))
            .padding(horizontal = 16.dp, vertical = 18.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(tr("의견을 남겨 주시면 ROCKY의 발전에 도움이 돼요", "Your feedback helps ROCKY improve"),
            fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = dark, textAlign = TextAlign.Center)
        Text(tr("선택 사항이에요", "Optional"), fontSize = 12.sp, color = Color(0xFF71717A))
        Spacer(Modifier.height(10.dp))
        OutlinedTextField(
            value = text, onValueChange = onChange,
            placeholder = { Text(tr("예: 드럼 필인이 원곡이랑 거의 같아요", "e.g. The drum fills match the song")) },
            minLines = 3, maxLines = 5,
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = dark, unfocusedTextColor = dark,
                focusedContainerColor = Color.White, unfocusedContainerColor = Color.White,
            ),
            modifier = Modifier.fillMaxWidth().testTag("rating_comment"),
        )
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = onSubmit, shape = ButtonShape,
            modifier = Modifier.fillMaxWidth().height(48.dp).testTag("comment_submit"),
        ) { Text(tr("제출", "Send"), fontWeight = FontWeight.Bold) }
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
 * 악보 그림의 위아래·양옆 빈 여백을 잘라낼 범위 (흰색이거나 투명한 칸은 여백으로 본다). null이면 자르지 않는다.
 * 여백이 크면 악보가 작고 휑해 보여서, 글자·음표가 있는 곳 둘레에 조금만 남긴다.
 * 잘라낸 만큼 서버의 마디 위치([PrintedMeasures])를 옮겨야 해서 범위를 돌려준다.
 */
internal fun marginCrop(src: android.graphics.Bitmap, pad: Int = 24): android.graphics.Rect? {
    val w = src.width
    val h = src.height
    if (w < 4 || h < 4) return null
    // 한 줄씩 읽고, 위·아래는 처음 만나는 글자에서, 양옆은 지금까지 찾은 범위 바깥만 본다.
    // 페이지 전체를 훑을 때보다 몇 배 빠르다 (여백은 대부분 바로 끝난다).
    val row = IntArray(w)
    fun ink(c: Int): Boolean {
        if (c ushr 24 < 40) return false
        return ((c shr 16 and 0xFF) * 3 + (c shr 8 and 0xFF) * 6 + (c and 0xFF)) / 10 <= 200
    }
    fun read(y: Int) = src.getPixels(row, 0, w, 0, y, w, 1)
    fun rowHasInk(y: Int): Boolean { read(y); return row.any { ink(it) } }
    val topY = (0 until h).firstOrNull { rowHasInk(it) } ?: return null
    val bottom = (h - 1 downTo topY).first { rowHasInk(it) }
    var left = w
    var right = -1
    for (y in topY..bottom) {
        read(y)
        var x = 0
        while (x < left) { if (ink(row[x])) { left = x; break }; x++ }
        x = w - 1
        while (x > right) { if (ink(row[x])) { right = x; break }; x-- }
    }
    if (right < 0) return null
    val l = (left - pad).coerceAtLeast(0)
    val t = (topY - pad).coerceAtLeast(0)
    val r = (right + pad).coerceAtMost(w - 1)
    val b = (bottom + pad).coerceAtMost(h - 1)
    return android.graphics.Rect(l, t, r + 1, b + 1)
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

/**
 * 파트 고르기. '전체'는 한 줄을 다 쓰고, 악기는 두 칸씩 줄을 나눈다 (옆으로 넘기지 않아도 다 보인다).
 * 기타가 2대면 기타 칸 하나를 '기타 1 | 기타 2'로 반씩 나눈다. 이름은 한 줄로만 쓴다(좁아도 세로로 쓰지 않음).
 */
/**
 * 결과 화면 악기 고르기. 자리는 늘 같다: 전체 / 피아노 · 드럼 / 베이스 · 기타.
 * 기타가 2대면 아래 줄을 베이스 · 기타 1 · 기타 2 세 칸으로 (한 줄의 칸은 너비가 같다).
 * 이 곡에 없는 악기는 회색으로 막아 둔다.
 */
@Composable
private fun PartGrid(
    instruments: List<String>,
    selected: String?,
    mark: (String) -> String,
    ai: Set<String>,
    warn: Set<String>,
    onSelect: (String?) -> Unit,
) {
    val rows = listOf(
        listOf("piano", "drums"),
        if (Demo.GUITAR2 in instruments) listOf("bass", "guitar", Demo.GUITAR2) else listOf("bass", "guitar"),
    )
    // 악보가 더 크게 보이도록 칸을 얇게 (세로 여백 4dp, 칸 사이 4dp).
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        PartChip(null, tr("전체", "All"), selected == null, ai = false, modifier = Modifier.fillMaxWidth()) { onSelect(null) }
        rows.forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                row.forEach { inst ->
                    val has = inst in instruments
                    PartChip(
                        inst, (if (has) mark(inst) else "") + Demo.label(inst, instruments), selected == inst,
                        ai = has && inst in ai, warn = has && inst in warn, enabled = has, modifier = Modifier.weight(1f),
                    ) { onSelect(inst) }
                }
            }
        }
    }
}

/** 파트 고르기 칸 하나. 악기 그림 + 이름 한 줄. [inst]가 null이면 '전체'. [enabled]가 false면 회색으로 막는다. */
@Composable
private fun PartChip(
    inst: String?, text: String, selected: Boolean, ai: Boolean, warn: Boolean = false,
    enabled: Boolean = true, modifier: Modifier = Modifier, onClick: () -> Unit,
) {
    val cs = MaterialTheme.colorScheme
    val fg = when {
        !enabled -> cs.onSurfaceVariant.copy(alpha = 0.45f)
        selected -> cs.onPrimary
        ai -> cs.secondary
        else -> cs.onSurface
    }
    val shape = RoundedCornerShape(8.dp)
    Row(
        modifier
            .card(
                shape, cs,
                bg = when {
                    !enabled -> cs.surfaceVariant.copy(alpha = 0.35f)
                    selected -> cs.primary
                    warn -> cs.error.copy(alpha = 0.16f)
                    ai -> cs.secondary.copy(alpha = 0.18f)
                    else -> cs.surface
                },
                line = if (selected) cs.primary else cs.outlineVariant,
            )
            .clickable(enabled = enabled, onClick = onClick)
            .semantics { if (!enabled) contentDescription = tr("$text · 이 곡에 없음", "$text · not in this song") }
            .padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        if (inst != null) {
            InstrumentIcon(inst, fg, size = 14.dp)
            Spacer(Modifier.width(5.dp))
        }
        Text(text, fontWeight = FontWeight.SemiBold, color = fg, maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 12.5.sp)
    }
}
