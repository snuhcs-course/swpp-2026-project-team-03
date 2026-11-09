package com.team3.rocky

import android.graphics.BitmapFactory
import android.media.MediaPlayer
import android.widget.Toast
import androidx.compose.animation.core.LinearEasing
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.layout.onSizeChanged
import com.team3.rocky.score.MeasureClock
import com.team3.rocky.score.MeasureLayout
import com.team3.rocky.score.ScoreLayout
import com.team3.rocky.server.LocalScore
import com.team3.rocky.server.PdfPages
import com.team3.rocky.server.ScoreStore
import com.team3.rocky.server.RockyApi
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
    onExport: () -> Unit,
    onShareToBand: () -> Unit,
    myPart: String? = null,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    var saved by remember { mutableStateOf(WorkStore.load(ctx).any { it.id == work.id }) }
    val ai = work.aiGenerated
    // 서버에서 만든 악보면 폰에 받아 둔 PDF·MIDI를, 아니면 데모 파일(assets/demo)을 쓴다.
    var local by remember(work.id) { mutableStateOf(ScoreStore.load(ctx, work.id)) }
    var changingKey by remember { mutableStateOf(false) }
    // 서버 결과는 기타 2를 따로 가질 수 있어서 파트 이름 그대로, 데모는 파일 이름(assetBase)으로.
    fun baseOf(part: String?) = part?.let { if (local != null) it else Demo.assetBase(it) } ?: Demo.BAND
    fun serverPart(base: String) = base.takeIf { it != Demo.BAND }
    // 밴드에서 열면 내 파트를 먼저 보여준다. 보컬처럼 악보가 없는 파트는 밴드 전체 악보를 보여준다.
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

    /** 선택한 파트의 음원을 준비한다. 위치는 그대로 이어서 재생할 수 있게 [startAt]으로 옮긴다. */
    fun load(base: String, startAt: Int): Boolean {
        // 서버 결과는 악보로 합성한 MP3(없으면 MIDI)를 들려준다.
        val currentScore = local
        val path = if (currentScore != null) currentScore.audio(serverPart(base))?.absolutePath
        else Assets.find(ctx, base, AUDIO_EXT)?.let { Assets.toCache(ctx, it).absolutePath }
        if (path == null) {
            Toast.makeText(ctx, "이 파트의 음원 파일이 없어요", Toast.LENGTH_SHORT).show()
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
            Toast.makeText(ctx, "재생할 수 없어요: ${e.message}", Toast.LENGTH_SHORT).show()
            loadedBase = null
            false
        }
    }

    val audioBase = baseOf(selectedPart)

    fun togglePlay() {
        if (playing) { player.pause(); playing = false; return }
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
    var pages by remember { mutableStateOf<List<androidx.compose.ui.graphics.ImageBitmap>?>(null) }
    // 마디 위치: 악보 그림에서 찾은 줄·마디선과, MIDI로 계산한 마디 시작 시간
    var measures by remember { mutableStateOf<MeasureLayout?>(null) }
    var clock by remember { mutableStateOf<MeasureClock?>(null) }
    val widthPx = with(LocalDensity.current) { LocalConfiguration.current.screenWidthDp.dp.roundToPx() }
    LaunchedEffect(scoreBase, local?.semitones) {
        pages = null
        measures = null
        // 키를 바꾸면 local이 새 결과로 바뀐다. 이번에 그릴 결과를 하나로 정해 둔다.
        val currentScore = local
        val bitmaps = withContext(Dispatchers.IO) {
            if (currentScore != null) {
                currentScore.pdf(serverPart(scoreBase))
                    ?.let { runCatching { PdfPages.render(it, widthPx) }.getOrNull() }
                    .orEmpty()
            } else Assets.pages(ctx, scoreBase).mapNotNull { n ->
                ctx.assets.open("${Demo.DIR}/$n").use { BitmapFactory.decodeStream(it) }
            }
        }
        pages = bitmaps.map { it.asImageBitmap() }
        // 악보를 먼저 보여 주고, 마디 위치는 그 뒤에 찾는다 (페이지가 많으면 1–2초 걸린다).
        val c = withContext(Dispatchers.IO) {
            // 파트 MIDI가 없으면 밴드 전체 MIDI로 센다 (박자와 템포는 파트마다 같다).
            val midi = if (currentScore != null) currentScore.midi(serverPart(scoreBase)) ?: currentScore.midi(null)
            else Assets.find(ctx, Demo.BAND, listOf("mid"))?.let { Assets.toCache(ctx, it) }
            MeasureClock.fromFile(midi)
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
    var scoreWidthPx by remember { mutableIntStateOf(0) }
    val currentMeasure = clock?.measureAt(position.toLong())
    val currentBox = currentMeasure?.let { measures?.box(it) }
    /** 악보 그림의 픽셀 좌표 → 스크롤 위치. 그림은 화면 너비에 맞춰 늘어난다. */
    fun scrollY(page: Int, y: Int): Int {
        val list = pages ?: return 0
        if (scoreWidthPx == 0) return 0
        var offset = 0f
        for (i in 0 until page.coerceAtMost(list.size)) offset += list[i].height * scoreWidthPx.toFloat() / list[i].width
        return (offset + y * scoreWidthPx.toFloat() / list[page.coerceIn(0, list.size - 1)].width).toInt()
    }
    val topMarginPx = with(LocalDensity.current) { 12.dp.roundToPx() }
    // '악보 따라가기': 지금 마디가 있는 줄이 바뀔 때마다 그 줄을 맨 위로 넘긴다.
    LaunchedEffect(currentBox?.page, currentBox?.top, follow, playing, scoreWidthPx) {
        val box = currentBox ?: return@LaunchedEffect
        if (follow && playing) {
            scoreScroll.animateScrollTo((scrollY(box.page, box.top) - topMarginPx).coerceAtLeast(0), tween(350))
        }
    }
    // 마디를 못 찾은 악보(MIDI가 없거나 줄을 못 읽음)는 예전처럼 재생 시간 비율로 내린다.
    LaunchedEffect(position, follow, playing, scoreScroll.maxValue, measures) {
        if (measures == null && follow && playing && duration > 0 && scoreScroll.maxValue > 0) {
            val target = (scoreScroll.maxValue * position.toFloat() / duration).toInt()
            scoreScroll.animateScrollTo(target, tween(200, easing = LinearEasing))
        }
    }

    Page(work.title, onBack, bottom = {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    WorkStore.add(ctx, work); saved = true; onSaved()
                    Toast.makeText(ctx, "보관함에 저장했어요. 보관함 탭에서 다시 볼 수 있어요", Toast.LENGTH_LONG).show()
                },
                enabled = !saved,
                modifier = Modifier.weight(1.2f).height(52.dp),
            ) { Text(if (saved) "보관함에 있음 ✓" else "보관함에 저장", maxLines = 1, fontSize = 14.sp) }
            OutlinedButton(onClick = onShareToBand, modifier = Modifier.weight(1f).height(52.dp)) {
                Text("밴드 공유", maxLines = 1, fontSize = 14.sp)
            }
            OutlinedButton(onClick = { player.pause(); playing = false; onExport() },
                enabled = !changingKey, modifier = Modifier.weight(1f).height(52.dp)) {
                Text("내보내기", maxLines = 1, fontSize = 14.sp)
            }
        }
    }) {
        // 파트 선택: 전체 + 각 파트
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            PartChip("전체", selectedPart == null, ai = false) { selectPart(null) }
            work.instruments.forEach { inst ->
                PartChip(
                    (if (inst in ai) "✨ " else "") + Demo.label(inst, work.instruments),
                    selectedPart == inst, ai = inst in ai,
                ) { selectPart(inst) }
            }
        }
        when {
            bandPart != null -> Note("밴드에서 내 파트(${Demo.label(bandPart, work.instruments)})를 먼저 보여드려요", cs.primary)
            myPart == Demo.VOCAL -> Note("보컬 파트는 밴드 전체 악보로 보여드려요", cs.primary)
        }
        if (ai.isNotEmpty()) Note("✨ AI 생성: 원곡에 없던 파트를 ROCKY가 새로 만들었어요", cs.onSurface)
        Spacer(Modifier.height(10.dp))

        if (saved && local != null) {
            Text("키 조정 · ${if (local!!.semitones == 0) "원키" else "${if (local!!.semitones > 0) "+" else ""}${local!!.semitones}반음"}",
                fontSize = 14.sp, fontWeight = FontWeight.Bold)
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((step, label) in listOf(-2 to "−한 키", -1 to "−반 키", 1 to "+반 키", 2 to "+한 키")) {
                    OutlinedButton(
                        onClick = {
                            val next = local!!.semitones + step
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
                                } catch (e: Exception) {
                                    Toast.makeText(ctx, "키를 바꾸지 못했어요: ${e.message}", Toast.LENGTH_LONG).show()
                                } finally {
                                    changingKey = false
                                }
                            }
                        },
                        enabled = !changingKey && local!!.semitones + step in -12..12,
                    ) { Text(label, maxLines = 1, fontSize = 12.sp) }
                }
            }
            if (changingKey) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("전체·악기별 악보와 음원을 다시 만드는 중…", fontSize = 12.sp)
                }
            }
            Text("낮은 개방현을 더 낮출 때는 타브의 줄 튜닝이 함께 바뀔 수 있어요.",
                fontSize = 11.sp, color = cs.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
        }

        // 플레이어: 재생/일시정지 + 위치 이동
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(cs.surface)
                .padding(start = 8.dp, end = 14.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilledIconButton(onClick = { togglePlay() }, enabled = !changingKey,
                modifier = Modifier.size(44.dp), shape = CircleShape) {
                Text(if (playing) "❚❚" else "▶", fontSize = 16.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Row {
                    Text(
                        "${selectedPart?.let { Demo.label(it, work.instruments) } ?: "밴드 전체"} 듣기",
                        fontSize = 13.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f),
                    )
                    val bar = clock?.let { c ->
                        val m = c.measureAt((dragging?.toLong() ?: position.toLong())) + 1
                        "${m}마디 / ${c.count} · "
                    }.orEmpty()
                    Text(
                        "$bar${mmss(dragging?.toInt() ?: position)} / ${if (duration > 0) mmss(duration) else "-:--"}",
                        fontSize = 12.sp, color = cs.onSurfaceVariant,
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
        if (duration == 0) {
            InfoNote("▶를 누르면 재생돼요. 막대를 끌어 원하는 곳으로 옮길 수 있어요.", Modifier.padding(top = 6.dp))
        }
        Row(Modifier.padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = follow, onCheckedChange = { follow = it })
            Text(
                if (measures != null) "연주 중인 마디에 맞춰 악보 넘기기" else "재생 위치에 맞춰 악보 넘기기",
                fontSize = 13.sp, modifier = Modifier.clickable { follow = !follow },
            )
        }

        // 선택한 파트 또는 밴드 전체 악보
        Box(
            Modifier.fillMaxWidth().weight(1f)
                .clip(RoundedCornerShape(16.dp))
                .background(Color.White)
                .onSizeChanged { scoreWidthPx = it.width },
            contentAlignment = Alignment.TopCenter,
        ) {
            val list = pages
            when {
                list == null -> CircularProgressIndicator(Modifier.padding(40.dp))
                list.isEmpty() -> Text(
                    if (local != null) "이 파트의 악보가 결과에 없어요" else "악보 이미지가 없어요\n(assets/demo/$scoreBase.png)",
                    color = Color.Gray, textAlign = TextAlign.Center, modifier = Modifier.padding(40.dp),
                )
                else -> Column(Modifier.verticalScroll(scoreScroll)) {
                    val highlight = cs.primary.copy(alpha = 0.16f)
                    val edge = cs.primary.copy(alpha = 0.7f)
                    list.forEachIndexed { i, bmp ->
                        // 재생을 시작한 뒤에는 연주 중인 마디에 색을 칠한다.
                        val box = currentBox?.takeIf { it.page == i && duration > 0 }
                        Image(
                            bitmap = bmp, contentDescription = "악보",
                            contentScale = ContentScale.FillWidth,
                            modifier = Modifier.fillMaxWidth().drawWithContent {
                                drawContent()
                                if (box != null) {
                                    val k = size.width / bmp.width
                                    val pad = 6f * k
                                    val tl = Offset(box.left * k, box.top * k - pad * 2)
                                    val sz = Size((box.right - box.left) * k, (box.bottom - box.top) * k + pad * 4)
                                    drawRect(highlight, tl, sz)
                                    drawRect(edge, Offset(tl.x, tl.y + sz.height - 3.dp.toPx()), Size(sz.width, 3.dp.toPx()))
                                }
                            },
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(4.dp))
    }
}

@Composable
private fun PartChip(text: String, selected: Boolean, ai: Boolean, onClick: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Box(
        Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(
                when {
                    selected -> cs.primary
                    ai -> cs.secondary.copy(alpha = 0.18f)
                    else -> cs.surface
                },
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text, fontWeight = FontWeight.Bold,
            color = if (selected) cs.onPrimary else if (ai) cs.secondary else cs.onSurface,
        )
    }
}

@Composable
private fun Note(text: String, color: Color) {
    Spacer(Modifier.height(6.dp))
    Text(text, fontSize = 14.sp, fontWeight = FontWeight.Medium, color = color)
}

// ---------- 6. 내보내기 ----------
private class ExportItem(val key: String, val label: String, val format: String, val make: () -> File?)

@Composable
fun ExportScreen(work: Work, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val title = safeFileName(work.title)
    val all = remember { Assets.list(ctx) }
    val local = remember(work.id) { ScoreStore.load(ctx, work.id) }

    val bandItems = remember {
        if (local != null) return@remember serverBandItems(ctx, local, title)
        listOfNotNull(
            ExportItem("band.pdf", "악보", "PDF") { Assets.toCache(ctx, "band.pdf", "${title}_밴드 전체.pdf") }
                .takeIf { "band.pdf" in all },
            ExportItem("band.mid", "MIDI", "MID") { Assets.toCache(ctx, "band.mid", "${title}_밴드 전체.mid") }
                .takeIf { "band.mid" in all },
            ExportItem("band.mp3", "음원", "MP3") { Assets.toCache(ctx, "band.mp3", "${title}_밴드 전체.mp3") }
                .takeIf { "band.mp3" in all },
        )
    }
    val partItems = remember {
        if (local != null) return@remember serverPartItems(ctx, local, work, title)
        work.instruments.associateWith { inst ->
            val base = Demo.assetBase(inst)
            val name = Demo.label(inst, work.instruments)
            listOfNotNull(
                ExportItem("$inst.pdf", "악보", "PDF") { Assets.pagesToPdf(ctx, base, "${title}_$name.pdf") }
                    .takeIf { Assets.pages(ctx, base).isNotEmpty() },
                ExportItem("$inst.mp3", "음원", "MP3") { Assets.toCache(ctx, "$base.mp3", "${title}_$name.mp3") }
                    .takeIf { "$base.mp3" in all },
            )
        }.filterValues { it.isNotEmpty() }
    }
    val checked = remember { mutableStateMapOf<String, Boolean>().apply { put("band.pdf", true) } }
    var busy by remember { mutableStateOf(false) }
    val count = checked.count { it.value }

    Page("내보내기", onBack, bottom = {
        Button(
            onClick = {
                busy = true
                scope.launch {
                    val items = (bandItems + partItems.values.flatten()).filter { checked[it.key] == true }
                    val files = try {
                        withContext(Dispatchers.IO) { items.mapNotNull { it.make() } }
                    } catch (e: Exception) {
                        Toast.makeText(ctx, "파일을 만들지 못했어요: ${e.message}", Toast.LENGTH_SHORT).show()
                        emptyList()
                    }
                    busy = false
                    shareFiles(ctx, files)
                }
            },
            enabled = count > 0 && !busy,
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = cs.onPrimary)
            else Text(if (count > 0) "${count}개 파일 보내기" else "보낼 파일을 골라주세요", fontSize = 17.sp)
        }
    }) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            Text("어떤 파일을 보낼까요?", fontSize = 26.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))
            // 곡 제목과 파트를 나눠서 보여준다.
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(cs.surface).padding(14.dp)) {
                Text("곡", fontSize = 12.sp, color = cs.onSurfaceVariant)
                Text(work.title, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text("파트", fontSize = 12.sp, color = cs.onSurfaceVariant)
                Text(Demo.labels(work.instruments))
            }
            Spacer(Modifier.height(6.dp))
            InfoNote("카카오톡 · 메일 · 드라이브 등으로 보내거나 폰에 저장할 수 있어요.")

            Spacer(Modifier.height(20.dp))
            Text("밴드 전체", fontWeight = FontWeight.Bold, color = cs.primary, fontSize = 14.sp)
            Spacer(Modifier.height(6.dp))
            bandItems.forEach { ExportRow(it, checked) }
            if (bandItems.isEmpty()) Text("보낼 수 있는 밴드 전체 파일이 없어요", color = cs.onSurfaceVariant)

            partItems.forEach { (inst, items) ->
                Spacer(Modifier.height(16.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    InstrumentIcon(inst, cs.primary, size = 18.dp)
                    Spacer(Modifier.width(6.dp))
                    Text(Demo.label(inst, work.instruments), fontWeight = FontWeight.Bold, color = cs.primary, fontSize = 14.sp)
                    if (inst in work.aiGenerated) Text("  ✨ AI 생성", fontSize = 12.sp, color = cs.secondary)
                }
                Spacer(Modifier.height(6.dp))
                items.forEach { ExportRow(it, checked) }
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}

@Composable
private fun ExportRow(item: ExportItem, checked: MutableMap<String, Boolean>) {
    val cs = MaterialTheme.colorScheme
    val on = checked[item.key] == true
    Row(
        Modifier.fillMaxWidth()
            .padding(vertical = 4.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(cs.surface)
            .border(BorderStroke(1.dp, if (on) cs.primary else Color.Transparent), RoundedCornerShape(14.dp))
            .clickable { checked[item.key] = !on }
            .padding(horizontal = 8.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = on, onCheckedChange = { checked[item.key] = it })
        Text(item.label, fontWeight = FontWeight.Bold)
        Spacer(Modifier.weight(1f))
        Text(item.format, fontSize = 12.sp, color = cs.primary, modifier = Modifier.padding(end = 12.dp))
    }
}

// ----- 서버에서 받은 결과 내보내기 -----
private fun serverBandItems(ctx: android.content.Context, local: LocalScore, title: String) = listOfNotNull(
    local.pdf(null)?.let { f -> ExportItem("band.pdf", "악보", "PDF") { ScoreStore.toShare(ctx, f, "${title}_밴드 전체.pdf") } },
    local.midi(null)?.let { f -> ExportItem("band.mid", "MIDI", "MID") { ScoreStore.toShare(ctx, f, "${title}_밴드 전체.mid") } },
    local.mp3(null)?.let { f -> ExportItem("band.mp3", "음원", "MP3") { ScoreStore.toShare(ctx, f, "${title}_밴드 전체.mp3") } },
)

private fun serverPartItems(
    ctx: android.content.Context, local: LocalScore, work: Work, title: String,
): Map<String, List<ExportItem>> =
    work.instruments.associateWith { inst ->
        val name = Demo.label(inst, work.instruments)
        listOfNotNull(
            local.pdf(inst)?.let { f -> ExportItem("$inst.pdf", "악보", "PDF") { ScoreStore.toShare(ctx, f, "${title}_$name.pdf") } },
            local.midi(inst)?.let { f -> ExportItem("$inst.mid", "MIDI", "MID") { ScoreStore.toShare(ctx, f, "${title}_$name.mid") } },
            local.mp3(inst)?.let { f -> ExportItem("$inst.mp3", "음원", "MP3") { ScoreStore.toShare(ctx, f, "${title}_$name.mp3") } },
        )
    }.filterValues { it.isNotEmpty() }
