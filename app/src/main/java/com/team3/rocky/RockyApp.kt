@file:OptIn(ExperimentalMaterial3Api::class)

package com.team3.rocky

import android.graphics.BitmapFactory
import android.media.MediaPlayer
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ---------- 화면 목록 ----------
sealed class Screen {
    object Home : Screen()                                        // 1. 홈
    object Storage : Screen()                                     // 1-2. 보관함
    object Instruments : Screen()                                 // 2. 악기 선택
    object Upload : Screen()                                      // 3. 음원 업로드
    object Processing : Screen()                                  // 4. 처리 중
    class Result(val work: Work, val fresh: Boolean) : Screen()   // 5. 결과
    class Export(val work: Work) : Screen()                       // 6. 내보내기
}

@Composable
fun RockyApp() {
    val stack = remember { mutableStateListOf<Screen>(Screen.Home) }
    var selected by remember { mutableStateOf(setOf<String>()) }
    var songTitle by remember { mutableStateOf("") }

    fun go(s: Screen) { stack.add(s) }
    fun back() { if (stack.size > 1) stack.removeAt(stack.lastIndex) }

    BackHandler(enabled = stack.size > 1) { back() }

    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        when (val s = stack.last()) {
            Screen.Home -> HomeScreen(
                onNew = { selected = emptySet(); songTitle = ""; go(Screen.Instruments) },
                onStorage = { go(Screen.Storage) },
            )
            Screen.Storage -> StorageScreen(
                onBack = { back() },
                onOpen = { go(Screen.Result(it, fresh = false)) },
            )
            Screen.Instruments -> InstrumentScreen(
                selected = selected,
                onToggle = { i -> selected = if (i in selected) selected - i else selected + i },
                onBack = { back() },
                onNext = { go(Screen.Upload) },
            )
            Screen.Upload -> UploadScreen(
                onBack = { back() },
                onStart = { title -> songTitle = title; go(Screen.Processing) },
            )
            Screen.Processing -> ProcessingScreen(
                title = songTitle,
                onDone = {
                    val work = Work(
                        id = System.currentTimeMillis(),
                        title = songTitle,
                        instruments = Demo.INSTRUMENTS.filter { it in selected },
                        date = SimpleDateFormat("yyyy.MM.dd HH:mm", Locale.KOREA).format(Date()),
                    )
                    stack.removeAt(stack.lastIndex)          // 처리 중 화면은 뒤로가기에서 제외
                    go(Screen.Result(work, fresh = true))
                },
            )
            is Screen.Result -> ResultScreen(
                work = s.work,
                fresh = s.fresh,
                onBack = { back() },
                onExport = { go(Screen.Export(s.work)) },
            )
            is Screen.Export -> ExportScreen(work = s.work, onBack = { back() })
        }
    }
}

// ---------- 공통 화면 틀 ----------
@Composable
fun Page(
    title: String,
    onBack: (() -> Unit)?,
    bottom: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text(title, fontWeight = FontWeight.Bold, maxLines = 1) },
                navigationIcon = {
                    if (onBack != null) TextButton(onClick = onBack) { Text("←", fontSize = 22.sp) }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
        bottomBar = {
            if (bottom != null) Box(Modifier.padding(20.dp)) { bottom() }
        },
    ) { pad ->
        Column(
            Modifier.padding(pad).fillMaxSize().padding(horizontal = 20.dp),
            content = content,
        )
    }
}

// ---------- 1. 홈 ----------
@Composable
fun HomeScreen(onNew: () -> Unit, onStorage: () -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val count = remember { WorkStore.load(ctx).size }
    Column(Modifier.fillMaxSize().padding(24.dp)) {
        Spacer(Modifier.height(48.dp))
        Text("ROCKY", fontSize = 48.sp, fontWeight = FontWeight.Black, color = cs.primary)
        Text("어떤 곡이든, 우리 밴드 악보로", fontSize = 16.sp, color = cs.onSurfaceVariant)
        Spacer(Modifier.height(48.dp))
        BigCard("NEW", "새 악보 만들기", "음원을 올리면 밴드 악보로 바꿔드려요", cs.primary, cs.onPrimary, onNew)
        Spacer(Modifier.height(16.dp))
        BigCard("STORAGE", "보관함", "저장한 악보 ${count}개", cs.surfaceVariant, cs.onSurface, onStorage)
    }
}

@Composable
fun BigCard(tag: String, title: String, sub: String, bg: Color, fg: Color, onClick: () -> Unit) {
    Column(
        Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(bg)
            .clickable(onClick = onClick)
            .padding(24.dp)
    ) {
        Text(tag, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = fg.copy(alpha = 0.7f))
        Spacer(Modifier.height(8.dp))
        Text(title, fontSize = 26.sp, fontWeight = FontWeight.Bold, color = fg)
        Spacer(Modifier.height(4.dp))
        Text(sub, fontSize = 14.sp, color = fg.copy(alpha = 0.8f))
    }
}

// ---------- 1-2. 보관함 ----------
@Composable
fun StorageScreen(onBack: () -> Unit, onOpen: (Work) -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val works = remember { WorkStore.load(ctx) }
    Page("보관함", onBack) {
        if (works.isEmpty()) {
            Spacer(Modifier.height(80.dp))
            Text(
                "아직 저장한 악보가 없어요.\n홈에서 NEW로 첫 악보를 만들어 보세요.",
                color = cs.onSurfaceVariant, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth(),
            )
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(works) { w ->
                    Column(
                        Modifier.fillMaxWidth()
                            .clip(RoundedCornerShape(16.dp))
                            .background(cs.surface)
                            .clickable { onOpen(w) }
                            .padding(18.dp)
                    ) {
                        Text(w.title, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                        Spacer(Modifier.height(4.dp))
                        Text(
                            w.instruments.joinToString(" · ") { Demo.kor(it) } + "   |   " + w.date,
                            fontSize = 13.sp, color = cs.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

// ---------- 2. 악기 선택 ----------
@Composable
fun InstrumentScreen(
    selected: Set<String>,
    onToggle: (String) -> Unit,
    onBack: () -> Unit,
    onNext: () -> Unit,
) {
    val cs = MaterialTheme.colorScheme
    Page("새 악보", onBack, bottom = {
        Button(
            onClick = onNext, enabled = selected.isNotEmpty(),
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) { Text("다음  (${selected.size}개 선택)", fontSize = 17.sp) }
    }) {
        Text("당신을 위한 악보를\n만드세요", fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp)
        Spacer(Modifier.height(8.dp))
        Text("연주할 악기를 골라주세요 · 여러 개 선택 가능", color = cs.onSurfaceVariant)
        Spacer(Modifier.height(28.dp))
        Demo.INSTRUMENTS.chunked(2).forEach { row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                row.forEach { inst ->
                    InstrumentTile(inst, inst in selected, Modifier.weight(1f)) { onToggle(inst) }
                }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
fun InstrumentTile(inst: String, on: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(20.dp)
    Column(
        modifier.height(140.dp)
            .clip(shape)
            .background(if (on) cs.primary else cs.surface)
            .border(BorderStroke(2.dp, if (on) cs.primary else cs.surfaceVariant), shape)
            .clickable(onClick = onClick)
            .padding(18.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(Demo.emoji(inst), fontSize = 36.sp)
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                Demo.kor(inst), fontSize = 19.sp, fontWeight = FontWeight.Bold,
                color = if (on) cs.onPrimary else cs.onSurface,
            )
            Spacer(Modifier.weight(1f))
            if (on) Text("✓", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = cs.onPrimary)
        }
    }
}

// ---------- 3. 음원 업로드 ----------
@Composable
fun UploadScreen(onBack: () -> Unit, onStart: (String) -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    var picked by remember { mutableStateOf<String?>(null) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) picked = displayName(ctx, uri)
    }
    val shape = RoundedCornerShape(24.dp)
    Page("음원 업로드", onBack, bottom = {
        Button(
            onClick = { onStart(picked ?: Demo.SONG_TITLE) }, enabled = picked != null,
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) { Text("악보 만들기 시작", fontSize = 17.sp) }
    }) {
        Text("어떤 곡으로\n만들까요?", fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp)
        Spacer(Modifier.height(8.dp))
        Text("MP3 · WAV 음원 파일을 올려주세요", color = cs.onSurfaceVariant)
        Spacer(Modifier.height(28.dp))
        Column(
            Modifier.fillMaxWidth().height(190.dp)
                .clip(shape)
                .background(cs.surface)
                .border(BorderStroke(2.dp, if (picked == null) cs.surfaceVariant else cs.primary), shape)
                .clickable { launcher.launch("audio/*") }
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(if (picked == null) "＋" else "♪", fontSize = 44.sp, color = cs.primary)
            Spacer(Modifier.height(8.dp))
            Text(
                picked ?: "눌러서 음원 파일 선택",
                fontWeight = FontWeight.Bold, textAlign = TextAlign.Center,
                color = if (picked == null) cs.onSurfaceVariant else cs.onSurface,
            )
        }
        Spacer(Modifier.height(16.dp))
        OutlinedButton(onClick = { picked = Demo.SONG_TITLE }, modifier = Modifier.fillMaxWidth().height(50.dp)) {
            Text("데모 곡으로 체험하기")
        }
        Spacer(Modifier.height(16.dp))
        Text(
            "※ Iteration 1 시연 버전: 어떤 파일을 올려도 미리 준비한 데모 결과가 표시돼요.",
            fontSize = 12.sp, color = cs.onSurfaceVariant,
        )
    }
}

// ---------- 4. 처리 중 (시연용 애니메이션) ----------
@Composable
fun ProcessingScreen(title: String, onDone: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val steps = listOf(
        "채보 중" to "음원에서 악기별 음을 찾고 있어요",
        "박자 맞추는 중" to "박과 마디 위치를 찾고 있어요",
        "밴드 편곡 중" to "고른 악기로 악보를 만들고 있어요",
    )
    var current by remember { mutableStateOf(0) }
    LaunchedEffect(Unit) {
        for (i in steps.indices) {
            current = i
            delay(2200)
        }
        current = steps.size
        delay(600)
        onDone()
    }
    val progress by animateFloatAsState(targetValue = current / steps.size.toFloat())

    Column(
        Modifier.fillMaxSize().padding(28.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(title, fontSize = 15.sp, color = cs.onSurfaceVariant, maxLines = 1)
        Spacer(Modifier.height(6.dp))
        Text("악보를 만드는 중이에요", fontSize = 26.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(36.dp))
        steps.forEachIndexed { i, (name, desc) ->
            Row(Modifier.padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(40.dp), contentAlignment = Alignment.Center) {
                    when {
                        i < current -> Text("✓", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = cs.primary)
                        i == current -> CircularProgressIndicator(Modifier.size(30.dp), strokeWidth = 3.dp)
                        else -> Text("${i + 1}", fontSize = 18.sp, color = cs.onSurfaceVariant)
                    }
                }
                Spacer(Modifier.width(16.dp))
                Column {
                    Text(
                        name, fontSize = 19.sp, fontWeight = FontWeight.Bold,
                        color = if (i <= current) cs.onSurface else cs.onSurfaceVariant,
                    )
                    Text(desc, fontSize = 13.sp, color = cs.onSurfaceVariant)
                }
            }
        }
        Spacer(Modifier.height(32.dp))
        Box(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)).background(cs.surfaceVariant)) {
            Box(Modifier.fillMaxWidth(progress).height(8.dp).background(cs.primary))
        }
    }
}

// ---------- 5. 결과 (밴드 전체 악보 + 전체 재생) ----------
@Composable
fun ResultScreen(work: Work, fresh: Boolean, onBack: () -> Unit, onExport: () -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    var saved by remember { mutableStateOf(!fresh) }
    var playing by remember { mutableStateOf(false) }
    val player = remember { MediaPlayer() }
    DisposableEffect(Unit) { onDispose { player.release() } }

    fun togglePlay() {
        if (playing) {
            player.stop(); player.reset(); playing = false
            return
        }
        val name = Assets.find(ctx, Demo.BAND, AUDIO_EXT)
        if (name == null) {
            Toast.makeText(ctx, "assets/demo/${Demo.BAND}.mp3 파일이 없어요", Toast.LENGTH_SHORT).show()
            return
        }
        try {
            player.reset()
            player.setDataSource(Assets.toCache(ctx, name).absolutePath)
            player.prepare()
            player.setOnCompletionListener { playing = false }
            player.start()
            playing = true
        } catch (e: Exception) {
            Toast.makeText(ctx, "재생 실패: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    // 밴드 전체 악보: band.png 하나 또는 MuseScore가 나눠 저장한 band-1.png, band-2.png ...
    val pages = remember {
        val pageNo = Regex("^${Demo.BAND}(-(\\d+))?\\.(png|jpg|jpeg|webp)$")
        Assets.list(ctx)
            .mapNotNull { n -> pageNo.find(n)?.let { m -> (m.groupValues[2].toIntOrNull() ?: 0) to n } }
            .sortedBy { it.first }
            .mapNotNull { (_, n) -> ctx.assets.open("${Demo.DIR}/$n").use { BitmapFactory.decodeStream(it) } }
    }

    Page(work.title, onBack, bottom = {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = { WorkStore.add(ctx, work); saved = true }, enabled = !saved,
                modifier = Modifier.weight(1f).height(52.dp),
            ) { Text(if (saved) "저장됨 ✓" else "저장") }
            OutlinedButton(onClick = onExport, modifier = Modifier.weight(1f).height(52.dp)) {
                Text("내보내기")
            }
        }
    }) {
        // 악기 구성 표시 (AI가 새로 만든 악기는 ✨)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            work.instruments.forEach { inst ->
                val ai = inst in Demo.AI_GENERATED
                Box(
                    Modifier.weight(1f)
                        .clip(RoundedCornerShape(12.dp))
                        .background(if (ai) cs.secondary.copy(alpha = 0.18f) else cs.surface)
                        .padding(vertical = 10.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        (if (ai) "✨ " else "") + Demo.kor(inst), fontWeight = FontWeight.Bold,
                        color = if (ai) cs.secondary else cs.onSurface,
                    )
                }
            }
        }
        if (work.instruments.any { it in Demo.AI_GENERATED }) {
            Spacer(Modifier.height(6.dp))
            Text("✨ AI 생성: 원곡에 없던 파트를 ROCKY가 새로 만들었어요", fontSize = 12.sp, color = cs.onSurfaceVariant)
        }
        Spacer(Modifier.height(12.dp))

        // 전체 재생
        Button(onClick = { togglePlay() }, modifier = Modifier.fillMaxWidth().height(50.dp)) {
            Text(if (playing) "■ 정지" else "▶ 밴드 전체 듣기", fontSize = 16.sp)
        }
        Spacer(Modifier.height(12.dp))

        // 밴드 전체 악보
        Box(
            Modifier.fillMaxWidth().weight(1f)
                .clip(RoundedCornerShape(16.dp))
                .background(Color.White),
            contentAlignment = Alignment.TopCenter,
        ) {
            if (pages.isNotEmpty()) {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    pages.forEach { bmp ->
                        Image(
                            bitmap = bmp.asImageBitmap(), contentDescription = "밴드 악보",
                            modifier = Modifier.fillMaxWidth(), contentScale = ContentScale.FillWidth,
                        )
                    }
                }
            } else {
                Text(
                    "악보 이미지가 없어요\n(assets/demo/${Demo.BAND}.png)",
                    color = Color.Gray, textAlign = TextAlign.Center, modifier = Modifier.padding(40.dp),
                )
            }
        }
    }
}

// ---------- 6. 내보내기 ----------
@Composable
fun ExportScreen(work: Work, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val files = remember {
        val all = Assets.list(ctx)
        listOf("${Demo.BAND}.pdf" to "밴드 악보", "${Demo.BAND}.mid" to "밴드 MIDI").filter { it.first in all }
    }
    val checked = remember { mutableStateMapOf<String, Boolean>().apply { files.forEach { put(it.first, true) } } }

    Page("내보내기", onBack, bottom = {
        Button(
            onClick = { shareFiles(ctx, files.map { it.first }.filter { checked[it] == true }) },
            enabled = checked.values.any { it },
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) { Text("공유하기", fontSize = 17.sp) }
    }) {
        Text("어떤 파일을 보낼까요?", fontSize = 26.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        Text(work.title + " · " + work.instruments.joinToString(" · ") { Demo.kor(it) }, color = cs.onSurfaceVariant)
        Spacer(Modifier.height(20.dp))
        if (files.isEmpty()) {
            Text("assets/demo/ 에 ${Demo.BAND}.pdf · ${Demo.BAND}.mid 파일이 없어요", color = cs.onSurfaceVariant)
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(files) { (name, label) ->
                Row(
                    Modifier.fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(cs.surface)
                        .clickable { checked[name] = checked[name] != true }
                        .padding(horizontal = 8.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(checked = checked[name] == true, onCheckedChange = { checked[name] = it })
                    Text(label, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.weight(1f))
                    Text(
                        name.substringAfterLast('.').uppercase(), fontSize = 12.sp,
                        color = cs.primary, modifier = Modifier.padding(end = 12.dp),
                    )
                }
            }
        }
    }
}
