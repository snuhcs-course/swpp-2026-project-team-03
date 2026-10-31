// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.band

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.widget.Toast
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.team3.rocky.Demo
import com.team3.rocky.Page
import com.team3.rocky.Work
import com.team3.rocky.WorkStore
import com.team3.rocky.auth.User
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ---------- 나의 밴드 (목록) ----------
@Composable
fun BandListScreen(
    user: User,
    repo: BandRepository,
    onBack: () -> Unit,
    onOpen: (Long) -> Unit,
    onAdd: () -> Unit,
) {
    val cs = MaterialTheme.colorScheme
    val bands by produceState<List<BandSummary>?>(null, user.id) { value = repo.myBands(user) }

    Page("나의 밴드", onBack, bottom = {
        Button(onClick = onAdd, modifier = Modifier.fillMaxWidth().height(56.dp).testTag("band_add")) {
            Text("+ 밴드 만들기 · 참여하기", fontSize = 17.sp)
        }
    }) {
        val list = bands
        when {
            list == null -> Loading()
            list.isEmpty() -> {
                Spacer(Modifier.height(64.dp))
                Text(
                    "아직 참여한 밴드가 없어요.\n밴드를 만들고 멤버에게 초대 코드를 보내 보세요.",
                    color = cs.onSurfaceVariant, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(24.dp))
                DemoHint()
            }
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(list, key = { it.band.id }) { s ->
                    Column(
                        Modifier.fillMaxWidth()
                            .clip(RoundedCornerShape(18.dp))
                            .background(cs.surface)
                            .clickable { onOpen(s.band.id) }
                            .padding(18.dp)
                            .testTag("band_${s.band.id}"),
                    ) {
                        Text(s.band.name, fontWeight = FontWeight.Bold, fontSize = 19.sp)
                        Spacer(Modifier.height(4.dp))
                        Text("멤버 ${s.memberCount}명 · 공유 악보 ${s.scoreCount}개", fontSize = 13.sp, color = cs.onSurfaceVariant)
                        Spacer(Modifier.height(10.dp))
                        PartBadge(s.myInstrument)
                    }
                }
                item { Spacer(Modifier.height(8.dp)); DemoHint() }
            }
        }
    }
}

// ---------- 밴드 만들기 · 참여하기 ----------
@Composable
fun BandJoinScreen(user: User, repo: BandRepository, onBack: () -> Unit, onDone: (Long) -> Unit) {
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    var joinMode by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    // 회원가입 때 고른 첫 악기를 기본 파트로 둔다.
    var instrument by remember { mutableStateOf(user.instruments.firstOrNull() ?: Demo.INSTRUMENTS.first()) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    fun submit() {
        if (busy) return
        focus.clearFocus()
        busy = true
        error = null
        scope.launch {
            val r = if (joinMode) repo.join(user, code, instrument) else repo.create(user, name, instrument)
            when (r) {
                is BandResult.Success -> onDone(r.band.id)
                is BandResult.Failure -> error = r.message
            }
            busy = false
        }
    }

    Page(if (joinMode) "밴드 참여하기" else "밴드 만들기", onBack, bottom = {
        Button(
            onClick = { submit() }, enabled = !busy,
            modifier = Modifier.fillMaxWidth().height(56.dp).testTag("band_submit"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = cs.onPrimary)
            else Text(if (joinMode) "참여하기" else "밴드 만들기", fontSize = 17.sp)
        }
    }) {
        Column(Modifier.imePadding().verticalScroll(rememberScrollState())) {
            Segmented(
                left = "새 밴드 만들기", right = "초대 코드로 참여",
                rightOn = joinMode, onChange = { joinMode = it; error = null },
            )
            Spacer(Modifier.height(28.dp))
            if (joinMode) {
                OutlinedTextField(
                    value = code,
                    // 입력 중에 글자를 바꾸면 키보드 입력이 꼬여서 글자가 빠진다. 대문자 변환은 참여할 때 한다.
                    onValueChange = { code = it.take(12); error = null },
                    label = { Text("초대 코드") },
                    placeholder = { Text("예: ${BandDatabase.DEMO_CODE}") },
                    singleLine = true, isError = error != null,
                    supportingText = { Text("멤버에게 받은 영문·숫자 ${BandRules.CODE_LENGTH}자리") },
                    keyboardOptions = KeyboardOptions(
                        capitalization = KeyboardCapitalization.Characters, imeAction = ImeAction.Done,
                    ),
                    keyboardActions = KeyboardActions(onDone = { submit() }),
                    modifier = Modifier.fillMaxWidth().testTag("band_code"),
                )
            } else {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.take(BandRules.NAME_MAX); error = null },
                    label = { Text("밴드 이름") },
                    singleLine = true, isError = error != null,
                    supportingText = { Text("${name.trim().length} / ${BandRules.NAME_MAX}") },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { focus.clearFocus() }),
                    modifier = Modifier.fillMaxWidth().testTag("band_name"),
                )
            }
            Spacer(Modifier.height(20.dp))
            Text("이 밴드에서 내 파트", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = cs.primary)
            Spacer(Modifier.height(4.dp))
            Text("공유된 악보를 열면 내 파트 악보가 먼저 보여요", fontSize = 13.sp, color = cs.onSurfaceVariant)
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Demo.INSTRUMENTS.forEach { inst ->
                    PartChip(inst, inst == instrument, Modifier.weight(1f)) { instrument = inst }
                }
            }
            error?.let {
                Spacer(Modifier.height(16.dp))
                Text(it, color = cs.error, fontSize = 14.sp, modifier = Modifier.testTag("band_error"))
            }
            if (joinMode) {
                Spacer(Modifier.height(24.dp))
                DemoHint()
            }
        }
    }
}

// ---------- 밴드 상세 ----------
@Composable
fun BandDetailScreen(
    user: User,
    repo: BandRepository,
    bandId: Long,
    onBack: () -> Unit,
    onOpenScore: (Work, String?) -> Unit,
    onShareScore: () -> Unit,
    onNewScore: (Set<String>) -> Unit,
    onLeft: () -> Unit,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val detail by produceState<BandDetail?>(null, bandId) { value = repo.detail(bandId) }
    var confirmLeave by remember { mutableStateOf(false) }
    val d = detail
    val myPart = d?.instrumentOf(user.id)

    Page(d?.band?.name ?: "밴드", onBack, bottom = {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(
                onClick = onShareScore, enabled = d != null,
                modifier = Modifier.weight(1f).height(52.dp).testTag("band_share_score"),
            ) { Text("악보 공유") }
            Button(
                onClick = { d?.let { onNewScore(it.members.map { m -> m.instrument }.toSet()) } },
                enabled = d != null,
                modifier = Modifier.weight(1f).height(52.dp).testTag("band_new_score"),
            ) { Text("이 밴드로 새 악보") }
        }
    }) {
        if (d == null) { Loading(); return@Page }
        Column(Modifier.verticalScroll(rememberScrollState())) {
            // 초대 코드
            Row(
                Modifier.fillMaxWidth()
                    .clip(RoundedCornerShape(18.dp))
                    .background(cs.surfaceVariant)
                    .padding(start = 18.dp, top = 14.dp, bottom = 14.dp, end = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("초대 코드", fontSize = 12.sp, color = cs.onSurfaceVariant)
                    Text(
                        d.band.inviteCode, fontSize = 26.sp, fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace, letterSpacing = 3.sp, color = cs.primary,
                        modifier = Modifier.testTag("band_invite_code"),
                    )
                }
                TextButton(onClick = {
                    ctx.getSystemService(ClipboardManager::class.java)
                        .setPrimaryClip(ClipData.newPlainText("ROCKY 초대 코드", d.band.inviteCode))
                }) { Text("복사") }
                TextButton(onClick = {
                    val text = "ROCKY에서 '${d.band.name}' 밴드에 들어와! 초대 코드: ${d.band.inviteCode}"
                    val send = Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text) }
                    ctx.startActivity(Intent.createChooser(send, "초대 코드 보내기"))
                }) { Text("보내기") }
            }

            Spacer(Modifier.height(28.dp))
            SectionTitle("멤버", d.members.size)
            d.members.forEach { m ->
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        Modifier.size(42.dp).clip(CircleShape).background(cs.surface),
                        contentAlignment = Alignment.Center,
                    ) { Text(Demo.emoji(m.instrument), fontSize = 20.sp) }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(m.nickname, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            if (m.userId == user.id) Tag("나", cs.primary)
                            if (m.isOwner) Tag("방장", cs.secondary)
                        }
                        Text(Demo.kor(m.instrument), fontSize = 13.sp, color = cs.onSurfaceVariant)
                    }
                }
            }

            Spacer(Modifier.height(24.dp))
            SectionTitle("공유된 악보", d.scores.size)
            if (d.scores.isEmpty()) {
                Text(
                    "아직 공유된 악보가 없어요.\n아래 '악보 공유'로 보관함의 악보를 올려 보세요.",
                    color = cs.onSurfaceVariant, fontSize = 14.sp, modifier = Modifier.padding(vertical = 12.dp),
                )
            }
            d.scores.forEach { s ->
                Column(
                    Modifier.fillMaxWidth()
                        .padding(vertical = 6.dp)
                        .clip(RoundedCornerShape(16.dp))
                        .background(cs.surface)
                        .clickable { onOpenScore(s.work, myPart) }
                        .padding(16.dp)
                        .testTag("band_score_${s.id}"),
                ) {
                    Text(s.work.title, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "${s.sharedByName}님이 공유 · ${DATE.format(Date(s.sharedAt))}",
                        fontSize = 13.sp, color = cs.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        s.work.instruments.forEach { inst ->
                            val mine = inst == myPart
                            Text(
                                (if (mine) "내 파트 · " else "") + Demo.kor(inst),
                                fontSize = 12.sp, fontWeight = if (mine) FontWeight.Bold else FontWeight.Normal,
                                color = if (mine) cs.onPrimary else cs.onSurfaceVariant,
                                modifier = Modifier
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(if (mine) cs.primary else cs.surfaceVariant)
                                    .padding(horizontal = 8.dp, vertical = 3.dp),
                            )
                        }
                    }
                }
            }

            Spacer(Modifier.height(20.dp))
            TextButton(onClick = { confirmLeave = true }, modifier = Modifier.testTag("band_leave")) {
                Text("밴드 나가기", color = cs.error)
            }
            Spacer(Modifier.height(8.dp))
        }
    }

    if (confirmLeave && d != null) {
        AlertDialog(
            onDismissRequest = { confirmLeave = false },
            confirmButton = {
                TextButton(onClick = {
                    confirmLeave = false
                    scope.launch {
                        repo.leave(user, d.band.id)
                        Toast.makeText(ctx, "'${d.band.name}'에서 나왔어요", Toast.LENGTH_SHORT).show()
                        onLeft()
                    }
                }, modifier = Modifier.testTag("band_leave_confirm")) { Text("나가기", color = cs.error) }
            },
            dismissButton = { TextButton(onClick = { confirmLeave = false }) { Text("취소") } },
            title = { Text("밴드에서 나갈까요?") },
            text = {
                Text(
                    if (d.members.size <= 1) "마지막 멤버라서 나가면 밴드와 공유된 악보가 모두 지워져요."
                    else "내가 공유한 악보는 밴드에 그대로 남아요. 초대 코드로 다시 들어올 수 있어요."
                )
            },
        )
    }
}

// ---------- 결과 화면에서: 어느 밴드에 공유할까요? ----------
@Composable
fun ShareToBandScreen(
    user: User,
    repo: BandRepository,
    work: Work,
    onBack: () -> Unit,
    onShared: () -> Unit,
    onAddBand: () -> Unit,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val bands by produceState<List<BandSummary>?>(null, user.id) { value = repo.myBands(user) }

    Page("밴드에 공유", onBack) {
        Text("어느 밴드에\n공유할까요?", fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp)
        Spacer(Modifier.height(6.dp))
        Text(work.title, color = cs.onSurfaceVariant, maxLines = 1)
        Spacer(Modifier.height(24.dp))
        val list = bands
        when {
            list == null -> Loading()
            list.isEmpty() -> {
                Text("아직 참여한 밴드가 없어요.", color = cs.onSurfaceVariant)
                Spacer(Modifier.height(16.dp))
                OutlinedButton(onClick = onAddBand, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                    Text("밴드 만들기 · 참여하기")
                }
            }
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(list, key = { it.band.id }) { s ->
                    Row(
                        Modifier.fillMaxWidth()
                            .clip(RoundedCornerShape(16.dp))
                            .background(cs.surface)
                            .clickable {
                                scope.launch {
                                    val added = repo.share(user, s.band.id, work)
                                    Toast.makeText(
                                        ctx,
                                        if (added) "'${s.band.name}'에 공유했어요" else "이미 '${s.band.name}'에 공유된 악보예요",
                                        Toast.LENGTH_SHORT,
                                    ).show()
                                    onShared()
                                }
                            }
                            .padding(18.dp)
                            .testTag("share_to_${s.band.id}"),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(s.band.name, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                            Text("멤버 ${s.memberCount}명", fontSize = 13.sp, color = cs.onSurfaceVariant)
                        }
                        Text("공유", color = cs.primary, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

// ---------- 밴드 화면에서: 보관함의 어떤 악보를 공유할까요? ----------
@Composable
fun PickScoreScreen(user: User, repo: BandRepository, bandId: Long, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val works = remember { WorkStore.load(ctx) }

    Page("악보 공유", onBack) {
        Text("보관함에서 악보를\n골라주세요", fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp)
        Spacer(Modifier.height(24.dp))
        if (works.isEmpty()) {
            Text(
                "보관함에 저장한 악보가 없어요.\n홈에서 새 악보를 만든 뒤 저장해 주세요.",
                color = cs.onSurfaceVariant,
            )
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(works, key = { it.id }) { w ->
                Column(
                    Modifier.fillMaxWidth()
                        .clip(RoundedCornerShape(16.dp))
                        .background(cs.surface)
                        .clickable {
                            scope.launch {
                                val added = repo.share(user, bandId, w)
                                Toast.makeText(
                                    ctx, if (added) "밴드에 공유했어요" else "이미 공유된 악보예요", Toast.LENGTH_SHORT,
                                ).show()
                                onBack()
                            }
                        }
                        .padding(18.dp),
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

// ---------- 공통 요소 ----------
private val DATE = SimpleDateFormat("yyyy.MM.dd", Locale.KOREA)

@Composable
private fun Loading() {
    Box(Modifier.fillMaxWidth().padding(top = 80.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

/** 서버가 없어서 친구를 초대할 수 없으니, 미리 넣어둔 예시 밴드로 들어가는 방법을 알려준다. */
@Composable
private fun DemoHint() {
    val cs = MaterialTheme.colorScheme
    Text(
        "※ 시연 버전: 초대 코드 ${BandDatabase.DEMO_CODE}로 예시 밴드에 참여해 볼 수 있어요. " +
            "지금은 같은 폰 안에서만 공유돼요.",
        fontSize = 12.sp, color = cs.onSurfaceVariant,
    )
}

@Composable
private fun SectionTitle(text: String, count: Int) {
    val cs = MaterialTheme.colorScheme
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(text, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.width(6.dp))
        Text("$count", fontSize = 16.sp, color = cs.primary, fontWeight = FontWeight.Bold)
    }
    Spacer(Modifier.height(6.dp))
}

@Composable
private fun Tag(text: String, color: androidx.compose.ui.graphics.Color) {
    Spacer(Modifier.width(6.dp))
    Text(
        text, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = color,
        modifier = Modifier
            .border(BorderStroke(1.dp, color), RoundedCornerShape(6.dp))
            .padding(horizontal = 6.dp, vertical = 1.dp),
    )
}

@Composable
private fun PartBadge(inst: String) {
    val cs = MaterialTheme.colorScheme
    Text(
        "내 파트  ${Demo.emoji(inst)} ${Demo.kor(inst)}",
        fontSize = 13.sp, fontWeight = FontWeight.Bold, color = cs.primary,
        modifier = Modifier
            .clip(RoundedCornerShape(10.dp))
            .background(cs.primary.copy(alpha = 0.14f))
            .padding(horizontal = 10.dp, vertical = 5.dp),
    )
}

@Composable
private fun PartChip(inst: String, on: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(14.dp)
    Column(
        modifier
            .clip(shape)
            .background(if (on) cs.primary else cs.surface)
            .border(BorderStroke(1.dp, if (on) cs.primary else cs.surfaceVariant), shape)
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp)
            .testTag("part_$inst"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(Demo.emoji(inst), fontSize = 22.sp)
        Text(
            Demo.kor(inst), fontSize = 13.sp, fontWeight = FontWeight.Bold,
            color = if (on) cs.onPrimary else cs.onSurface,
        )
    }
}

@Composable
private fun Segmented(left: String, right: String, rightOn: Boolean, onChange: (Boolean) -> Unit) {
    val cs = MaterialTheme.colorScheme
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(cs.surface).padding(4.dp),
    ) {
        listOf(false to left, true to right).forEach { (isRight, label) ->
            val on = isRight == rightOn
            Box(
                Modifier.weight(1f)
                    .clip(RoundedCornerShape(10.dp))
                    .background(if (on) cs.surfaceVariant else cs.surface)
                    .clickable { onChange(isRight) }
                    .padding(vertical = 12.dp)
                    .testTag(if (isRight) "mode_join" else "mode_create"),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    label, fontWeight = if (on) FontWeight.Bold else FontWeight.Normal,
                    color = if (on) cs.onSurface else cs.onSurfaceVariant,
                )
            }
        }
    }
}
