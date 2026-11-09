package com.team3.rocky

import android.Manifest
import android.graphics.BitmapFactory
import android.media.MediaPlayer
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import com.team3.rocky.server.PdfPages
import com.team3.rocky.server.ScoreStore
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
    // 원곡에 있다고 골랐지만 원곡에서 소리가 거의 들리지 않은 파트. 칩을 누르면 무슨 뜻인지 3초 동안 보여준다.
    val warn = work.unrecognized.toSet()
    var hint by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(hint) {
        if (hint != null) { kotlinx.coroutines.delay(3000); hint = null }
    }
    fun warnText(inst: String) = Demo.label(inst, work.instruments).let { name ->
        tr("⚠️ 원곡에서 $name 소리가 거의 들리지 않았어요. 악보에 음이 아주 적을 수 있어요",
            "⚠️ The $name was barely audible in the song. This score may have very few notes")
    }
    // 서버에서 만든 악보면 폰에 받아 둔 PDF·MIDI를, 아니면 데모 파일(assets/demo)을 쓴다.
    val local = remember(work.id) { ScoreStore.load(ctx, work.id) }
    // 서버 결과는 기타 2를 따로 가질 수 있어서 파트 이름 그대로, 데모는 파일 이름(assetBase)으로.
    fun baseOf(part: String?) = part?.let { if (local != null) it else Demo.assetBase(it) } ?: Demo.BAND
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

    /** 선택한 파트의 음원을 준비한다. 위치는 그대로 이어서 재생할 수 있게 [startAt]으로 옮긴다. */
    fun load(base: String, startAt: Int): Boolean {
        // 서버 결과는 악보로 합성한 MP3(없으면 MIDI)를 들려준다.
        val path = if (local != null) local.audio(serverPart(base))?.absolutePath
        else Assets.find(ctx, base, AUDIO_EXT)?.let { Assets.toCache(ctx, it).absolutePath }
        if (path == null) {
            Toast.makeText(ctx, tr("이 파트는 들을 수 있는 소리가 없어요", "No audio for this part"), Toast.LENGTH_SHORT).show()
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
    val widthPx = with(LocalDensity.current) { LocalConfiguration.current.screenWidthDp.dp.roundToPx() }
    LaunchedEffect(scoreBase) {
        pages = null
        pages = withContext(Dispatchers.IO) {
            if (local != null) {
                local.pdf(serverPart(scoreBase))
                    ?.let { runCatching { PdfPages.render(it, widthPx) }.getOrNull() }
                    .orEmpty().map { it.asImageBitmap() }
            } else Assets.pages(ctx, scoreBase).mapNotNull { n ->
                ctx.assets.open("${Demo.DIR}/$n").use { BitmapFactory.decodeStream(it) }?.asImageBitmap()
            }
        }
    }
    val scoreScroll = rememberScrollState()
    // '악보 따라가기': 재생 위치만큼 악보를 내린다. 마디 위치를 아는 게 아니라 비율로 맞추는 근사치다.
    LaunchedEffect(position, follow, playing, scoreScroll.maxValue) {
        if (follow && playing && duration > 0 && scoreScroll.maxValue > 0) {
            val target = (scoreScroll.maxValue * position.toFloat() / duration).toInt()
            scoreScroll.animateScrollTo(target, tween(200, easing = LinearEasing))
        }
    }

    Page(work.title, onBack, bottom = {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    WorkStore.add(ctx, work); saved = true; onSaved()
                    Toast.makeText(ctx, tr("보관함에 저장했어요", "Saved to your library"), Toast.LENGTH_SHORT).show()
                },
                enabled = !saved,
                modifier = Modifier.weight(1.1f).height(52.dp), contentPadding = TightButtonPadding,
            ) { Text(if (saved) tr("저장됨 ✓", "Saved ✓") else tr("보관함에 저장", "Save"), maxLines = 1, fontSize = 14.sp) }
            OutlinedButton(onClick = onShareToBand, modifier = Modifier.weight(1f).height(52.dp), contentPadding = TightButtonPadding) {
                Text(tr("밴드에 공유", "Share"), maxLines = 1, fontSize = 14.sp)
            }
            OutlinedButton(
                onClick = { player.pause(); playing = false; onExport() },
                modifier = Modifier.weight(1f).height(52.dp), contentPadding = TightButtonPadding,
            ) {
                Text(tr("파일 받기", "Get files"), maxLines = 1, fontSize = 14.sp)
            }
        }
    }) {
        // 악기를 하나씩 골라 들을 수 있다는 것을 맨 위에 한 줄로 알린다. ✨ 설명도 같은 줄에.
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                tr("악기를 누르면 그 악기만 들려요", "Tap an instrument to hear it alone"),
                fontSize = 14.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            // ✨·⚠️ 설명도 한 줄로. 둘 다 있으면 짧게 줄인다. 누르면 ⚠️ 뜻을 보여준다.
            val legend = listOfNotNull(
                if (ai.isEmpty()) null
                else if (warn.isEmpty()) tr("✨ AI가 만든 파트", "✨ Made by AI") else tr("✨ AI 생성", "✨ AI"),
                if (warn.isEmpty()) null else tr("⚠️ 소리가 거의 없음", "⚠️ Barely audible"),
            ).joinToString("  ")
            if (legend.isNotEmpty()) {
                Text(
                    legend, fontSize = 12.sp, color = cs.secondary, maxLines = 1,
                    modifier = Modifier.clickable(enabled = warn.isNotEmpty()) {
                        hint = tr(
                            "⚠️ 원곡에 있다고 고른 악기인데, 원곡에서 소리가 거의 들리지 않았어요",
                            "⚠️ You said the song has this instrument, but it was barely audible",
                        )
                    },
                )
            }
        }
        Spacer(Modifier.height(8.dp))
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            PartChip(null, tr("전체", "All"), selectedPart == null, ai = false) { selectPart(null) }
            work.instruments.forEach { inst ->
                val mark = when {
                    inst in warn -> "⚠️ "
                    inst in ai -> "✨ "
                    else -> ""
                }
                PartChip(
                    inst, mark + Demo.label(inst, work.instruments),
                    selectedPart == inst, ai = inst in ai, warn = inst in warn,
                ) {
                    selectPart(inst)
                    if (inst in warn) hint = warnText(inst)
                }
            }
        }
        Spacer(Modifier.height(10.dp))

        // 플레이어: 무엇을 듣는지 한 줄로 + 재생/일시정지 + 위치 이동
        val listening = selectedPart?.let { tr("${Demo.label(it, work.instruments)}만 듣기", "${Demo.label(it, work.instruments)} only") }
            ?: tr("밴드 전체 듣기", "Whole band")
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(cs.surface)
                .padding(start = 8.dp, end = 14.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilledIconButton(
                onClick = { togglePlay() }, modifier = Modifier.size(48.dp), shape = CircleShape,
            ) {
                Text(
                    if (playing) "❚❚" else "▶", fontSize = 16.sp, fontWeight = FontWeight.Bold,
                    modifier = Modifier.semantics { contentDescription = if (playing) tr("일시정지", "Pause") else tr("재생", "Play") },
                )
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        listening, fontSize = 13.sp, fontWeight = FontWeight.Bold, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                    )
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
        Row(
            Modifier.fillMaxWidth().padding(top = 2.dp).clip(RoundedCornerShape(10.dp)).clickable { follow = !follow },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Checkbox(checked = follow, onCheckedChange = { follow = it })
            Text(tr("들으면서 악보 자동으로 넘기기", "Scroll the score while playing"), fontSize = 13.sp, maxLines = 1,
                overflow = TextOverflow.Ellipsis)
        }

        // 선택한 파트 또는 밴드 전체 악보
        Box(
            Modifier.fillMaxWidth().weight(1f)
                .clip(RoundedCornerShape(16.dp))
                .background(Color.White),
            contentAlignment = Alignment.TopCenter,
        ) {
            val list = pages
            when {
                list == null -> CircularProgressIndicator(Modifier.padding(40.dp))
                list.isEmpty() -> Text(
                    tr("이 파트는 악보가 없어요", "No score for this part"),
                    color = Color.Gray, textAlign = TextAlign.Center, maxLines = 1, modifier = Modifier.padding(40.dp),
                )
                else -> Column(Modifier.verticalScroll(scoreScroll)) {
                    list.forEach { bmp ->
                        Image(
                            bitmap = bmp, contentDescription = tr("악보", "Score"),
                            modifier = Modifier.fillMaxWidth(), contentScale = ContentScale.FillWidth,
                        )
                    }
                }
            }
            // ⚠️ 뜻 안내. 악보 위에 잠깐 떠 있다가 3초 뒤 사라진다 (눌러도 닫힘).
            hint?.let { text ->
                Text(
                    text, fontSize = 13.sp, lineHeight = 18.sp, color = Color(0xFFF2F2F2), maxLines = 2,
                    modifier = Modifier.padding(10.dp).fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(Color(0xF02A2A33))
                        .clickable { hint = null }
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                )
            }
        }
        // 밴드 곡이 아니면 결과가 좋지 않을 수 있다는 것을 작게 알린다.
        Text(
            tr("밴드 악기로 연주한 곡이 아니면 악보가 정확하지 않을 수 있어요", "Scores may be less accurate for songs not played by a band"),
            fontSize = 11.sp, color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
        )
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
            .clip(RoundedCornerShape(12.dp))
            .background(
                when {
                    selected -> cs.primary
                    warn -> cs.error.copy(alpha = 0.16f)
                    ai -> cs.secondary.copy(alpha = 0.18f)
                    else -> cs.surface
                },
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

// ---------- 6. 파일 받기 (휴대폰에 저장 · 다른 앱으로 보내기) ----------
private class ExportItem(val key: String, val label: String, val format: String, val make: () -> File?)

private fun bandName() = tr("밴드 전체", "Full band")
private fun scoreLabel() = tr("악보", "Score")
private fun audioLabel() = tr("음원", "Audio")

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
        val band = bandName()
        listOfNotNull(
            ExportItem("band.pdf", scoreLabel(), "PDF") { Assets.toCache(ctx, "band.pdf", "${title}_$band.pdf") }
                .takeIf { "band.pdf" in all },
            ExportItem("band.mid", "MIDI", "MID") { Assets.toCache(ctx, "band.mid", "${title}_$band.mid") }
                .takeIf { "band.mid" in all },
            ExportItem("band.mp3", audioLabel(), "MP3") { Assets.toCache(ctx, "band.mp3", "${title}_$band.mp3") }
                .takeIf { "band.mp3" in all },
        )
    }
    val partItems = remember {
        if (local != null) return@remember serverPartItems(ctx, local, work, title)
        work.instruments.associateWith { inst ->
            val base = Demo.assetBase(inst)
            val name = Demo.label(inst, work.instruments)
            listOfNotNull(
                ExportItem("$inst.pdf", scoreLabel(), "PDF") { Assets.pagesToPdf(ctx, base, "${title}_$name.pdf") }
                    .takeIf { Assets.pages(ctx, base).isNotEmpty() },
                ExportItem("$inst.mp3", audioLabel(), "MP3") { Assets.toCache(ctx, "$base.mp3", "${title}_$name.mp3") }
                    .takeIf { "$base.mp3" in all },
            )
        }.filterValues { it.isNotEmpty() }
    }
    val checked = remember { mutableStateMapOf<String, Boolean>().apply { put("band.pdf", true) } }
    var busy by remember { mutableStateOf(false) }
    val count = checked.count { it.value }

    /** 고른 파일을 만든 뒤 [use]에 넘긴다 (휴대폰 저장 또는 공유). */
    fun withFiles(use: suspend (List<File>) -> Unit) {
        busy = true
        scope.launch {
            val items = (bandItems + partItems.values.flatten()).filter { checked[it.key] == true }
            val files = try {
                withContext(Dispatchers.IO) { items.mapNotNull { it.make() } }
            } catch (e: Exception) {
                Toast.makeText(ctx, tr("파일을 만들지 못했어요", "Couldn't prepare the files"), Toast.LENGTH_SHORT).show()
                emptyList()
            }
            if (files.isNotEmpty()) use(files)
            busy = false
        }
    }

    fun saveToPhone() = withFiles { files ->
        val n = withContext(Dispatchers.IO) { PhoneSaver.save(ctx, files) }
        val msg = if (n > 0) tr("${n}개 파일을 저장했어요 · ${PhoneSaver.folderLabel()}", "Saved $n ${plural(n, "file", "files")} · ${PhoneSaver.folderLabel()}")
        else tr("휴대폰에 저장하지 못했어요", "Couldn't save to your phone")
        Toast.makeText(ctx, msg, Toast.LENGTH_LONG).show()
    }

    // 안드로이드 8~9는 저장 권한을 먼저 받는다.
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) saveToPhone()
        else Toast.makeText(ctx, tr("저장하려면 저장 공간 권한이 필요해요", "Storage permission is needed to save"), Toast.LENGTH_LONG).show()
    }

    Page(tr("파일 받기", "Get files"), onBack, bottom = {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = { withFiles { shareFiles(ctx, it) } },
                enabled = count > 0 && !busy,
                modifier = Modifier.weight(1f).height(56.dp), contentPadding = TightButtonPadding,
            ) { Text(tr("다른 앱으로 보내기", "Send"), maxLines = 1, fontSize = 15.sp) }
            Button(
                onClick = {
                    if (PhoneSaver.needsPermission(ctx)) permission.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                    else saveToPhone()
                },
                enabled = count > 0 && !busy,
                modifier = Modifier.weight(1.2f).height(56.dp), contentPadding = TightButtonPadding,
            ) {
                if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = cs.onPrimary)
                else Text(tr("휴대폰에 저장", "Save to phone"), maxLines = 1, fontSize = 15.sp)
            }
        }
    }) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            Text(tr("어떤 파일을 받을까요?", "Which files do you want?"), fontSize = 26.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))
            Text(
                if (count > 0) tr("${count}개 골랐어요 · 저장하면 ${PhoneSaver.folderLabel()}", "$count selected · saved to ${PhoneSaver.folderLabel()}")
                else tr("받을 파일을 골라주세요", "Pick the files you want"),
                fontSize = 13.sp, color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(16.dp))
            Text(bandName(), fontWeight = FontWeight.Bold, color = cs.primary, fontSize = 14.sp)
            Spacer(Modifier.height(6.dp))
            bandItems.forEach { ExportRow(it, checked) }
            if (bandItems.isEmpty()) Text(tr("밴드 전체 파일이 없어요", "No full-band files"), color = cs.onSurfaceVariant)

            partItems.forEach { (inst, items) ->
                Spacer(Modifier.height(16.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    InstrumentIcon(inst, cs.primary, size = 18.dp)
                    Spacer(Modifier.width(6.dp))
                    Text(Demo.label(inst, work.instruments), fontWeight = FontWeight.Bold, color = cs.primary, fontSize = 14.sp)
                    if (inst in work.unrecognized) Text("  ⚠️ " + tr("원곡에서 소리가 거의 없음", "Barely audible in the song"), fontSize = 12.sp, color = cs.secondary)
                    else if (inst in work.aiGenerated) Text("  ✨ " + tr("AI가 만든 파트", "Made by AI"), fontSize = 12.sp, color = cs.secondary)
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

// ----- 서버에서 받은 결과 파일 -----
private fun serverBandItems(ctx: android.content.Context, local: LocalScore, title: String): List<ExportItem> {
    val band = bandName()
    return listOfNotNull(
        local.pdf(null)?.let { f -> ExportItem("band.pdf", scoreLabel(), "PDF") { ScoreStore.toShare(ctx, f, "${title}_$band.pdf") } },
        local.midi(null)?.let { f -> ExportItem("band.mid", "MIDI", "MID") { ScoreStore.toShare(ctx, f, "${title}_$band.mid") } },
        local.mp3(null)?.let { f -> ExportItem("band.mp3", audioLabel(), "MP3") { ScoreStore.toShare(ctx, f, "${title}_$band.mp3") } },
    )
}

private fun serverPartItems(
    ctx: android.content.Context, local: LocalScore, work: Work, title: String,
): Map<String, List<ExportItem>> =
    work.instruments.associateWith { inst ->
        val name = Demo.label(inst, work.instruments)
        listOfNotNull(
            local.pdf(inst)?.let { f -> ExportItem("$inst.pdf", scoreLabel(), "PDF") { ScoreStore.toShare(ctx, f, "${title}_$name.pdf") } },
            local.midi(inst)?.let { f -> ExportItem("$inst.mid", "MIDI", "MID") { ScoreStore.toShare(ctx, f, "${title}_$name.mid") } },
            local.mp3(inst)?.let { f -> ExportItem("$inst.mp3", audioLabel(), "MP3") { ScoreStore.toShare(ctx, f, "${title}_$name.mp3") } },
        )
    }.filterValues { it.isNotEmpty() }
