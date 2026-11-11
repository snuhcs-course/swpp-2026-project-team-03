// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.band

import android.content.ClipData
import android.content.ClipboardManager
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
import com.team3.rocky.ButtonShape
import com.team3.rocky.card
import com.team3.rocky.Demo
import com.team3.rocky.EmojiRow
import com.team3.rocky.InfoNote
import com.team3.rocky.InstrumentIcon
import com.team3.rocky.Page
import com.team3.rocky.TextInputDialog
import com.team3.rocky.TightButtonPadding
import com.team3.rocky.Work
import com.team3.rocky.WorkStore
import com.team3.rocky.tr
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
    onBack: (() -> Unit)?,
    onOpen: (Long) -> Unit,
    onAdd: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val cs = MaterialTheme.colorScheme
    val bands by produceState<List<BandSummary>?>(null, user.id) { value = repo.myBands(user) }

    Page(tr("나의 밴드", "Bands"), onBack, modifier = modifier, bottom = {
        Button(shape = ButtonShape, onClick = onAdd, modifier = Modifier.fillMaxWidth().height(56.dp).testTag("band_add")) {
            Text(tr("+ 밴드 만들기 · 참여하기", "+ Create or join a band"), fontSize = 17.sp)
        }
    }) {
        val list = bands
        when {
            list == null -> Loading()
            list.isEmpty() -> {
                Spacer(Modifier.height(64.dp))
                Text(
                    tr("참여한 밴드가 없어요.\n밴드를 만들고 초대 코드를 보내 보세요.", "No bands yet.\nCreate one and send the invite code."),
                    color = cs.onSurfaceVariant, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
                )
            }
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(list, key = { it.band.id }) { s ->
                    Column(
                        Modifier.fillMaxWidth()
                            .card(RoundedCornerShape(18.dp), cs)
                            .clickable { onOpen(s.band.id) }
                            .padding(18.dp)
                            .testTag("band_${s.band.id}"),
                    ) {
                        Text(s.band.name, fontWeight = FontWeight.Bold, fontSize = 19.sp, maxLines = 1)
                        Spacer(Modifier.height(4.dp))
                        Text(tr("멤버 ${s.memberCount}명 · 공유 악보 ${s.scoreCount}개", "${s.memberCount} members · ${s.scoreCount} shared scores"), fontSize = 13.sp, color = cs.onSurfaceVariant)
                        Spacer(Modifier.height(10.dp))
                        PartBadge(s.myInstrument)
                    }
                }
                item { Spacer(Modifier.height(8.dp)) }
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
    var instrument by remember { mutableStateOf(user.instruments.firstOrNull() ?: Demo.PARTS.first()) }
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

    Page(if (joinMode) tr("밴드 참여하기", "Join a band") else tr("밴드 만들기", "Create a band"), onBack, bottom = {
        Button(shape = ButtonShape,
            onClick = { submit() }, enabled = !busy,
            modifier = Modifier.fillMaxWidth().height(56.dp).testTag("band_submit"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = cs.onPrimary)
            else Text(if (joinMode) tr("참여하기", "Join") else tr("밴드 만들기", "Create a band"), fontSize = 17.sp)
        }
    }) {
        Column(Modifier.imePadding().verticalScroll(rememberScrollState())) {
            Segmented(
                left = tr("새 밴드 만들기", "Create new"), right = tr("초대 코드로 참여", "Join with code"),
                rightOn = joinMode, onChange = { joinMode = it; error = null },
            )
            Spacer(Modifier.height(28.dp))
            if (joinMode) {
                OutlinedTextField(
                    value = code,
                    // 입력 중에 글자를 바꾸면 키보드 입력이 꼬여서 글자가 빠진다. 대문자 변환은 참여할 때 한다.
                    onValueChange = { code = it.take(12); error = null },
                    label = { Text(tr("초대 코드", "Invite code")) },
                    placeholder = { Text(tr("예: ROCK26", "e.g. ROCK26")) },
                    singleLine = true, isError = error != null,
                    supportingText = { Text(tr("멤버에게 받은 영문·숫자 ${BandRules.CODE_LENGTH}자리", "The ${BandRules.CODE_LENGTH}-character code from a member")) },
                    keyboardOptions = KeyboardOptions(
                        capitalization = KeyboardCapitalization.Characters, imeAction = ImeAction.Done,
                    ),
                    keyboardActions = KeyboardActions(onDone = { submit() }),
                    modifier = Modifier.fillMaxWidth().testTag("band_code"),
                )
            } else {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = BandRules.limitName(it); error = null },
                    label = { Text(tr("밴드 이름", "Band name")) },
                    singleLine = true, isError = error != null,
                    supportingText = { Text("${BandRules.length(name.trim())} / ${BandRules.NAME_MAX}") },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { focus.clearFocus() }),
                    modifier = Modifier.fillMaxWidth().testTag("band_name"),
                )
                EmojiRow { e -> name = BandRules.limitName(name + e); error = null }
            }
            Spacer(Modifier.height(20.dp))
            Text(tr("이 밴드에서 내 파트", "Your part in this band"), fontSize = 13.sp, fontWeight = FontWeight.Bold, color = cs.primary)
            Spacer(Modifier.height(4.dp))
            Text(tr("공유 악보를 열면 내 파트가 먼저 보여요.", "Shared scores open on your part."), fontSize = 14.sp, color = cs.onSurface)
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Demo.PARTS.forEach { inst ->
                    PartChip(inst, inst == instrument, Modifier.weight(1f)) { instrument = inst }
                }
            }
            error?.let {
                Spacer(Modifier.height(16.dp))
                Text(it, color = cs.error, fontSize = 14.sp, modifier = Modifier.testTag("band_error"))
            }
            if (joinMode) {
                Spacer(Modifier.height(24.dp))
                InfoNote(tr("지금은 같은 휴대폰 안에서만 공유돼요", "For now, sharing works only on this phone"))
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
    onNewScore: (List<String>) -> Unit,
    onLeft: () -> Unit,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    // 이름을 바꾸면 숫자를 올려서 다시 읽는다.
    var version by remember { mutableStateOf(0) }
    val detail by produceState<BandDetail?>(null, bandId, version) { value = repo.detail(bandId) }
    var confirmLeave by remember { mutableStateOf(false) }
    var renamingBand by remember { mutableStateOf(false) }
    var renamingScore by remember { mutableStateOf<SharedScore?>(null) }
    val d = detail
    val myPart = d?.instrumentOf(user.id)
    val isOwner = d != null && d.band.ownerId == user.id

    Page(d?.band?.name ?: tr("밴드", "Band"), onBack, actions = {
        // 방장만 밴드 이름을 바꿀 수 있다.
        if (isOwner) TextButton(onClick = { renamingBand = true }, modifier = Modifier.testTag("band_rename")) {
            Text(tr("이름 수정", "Rename"))
        }
    }, bottom = {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(shape = ButtonShape,
                onClick = onShareScore, enabled = d != null,
                modifier = Modifier.weight(1f).height(52.dp).testTag("band_share_score"), contentPadding = TightButtonPadding,
            ) { Text(tr("악보 공유", "Share a score")) }
            Button(shape = ButtonShape,
                onClick = { d?.let { onNewScore(it.members.map { m -> m.instrument }) } },
                enabled = d != null,
                modifier = Modifier.weight(1f).height(52.dp).testTag("band_new_score"), contentPadding = TightButtonPadding,
            ) { Text(tr("이 밴드로 새 악보", "New score for this band")) }
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
                    Text(tr("초대 코드", "Invite code"), fontSize = 12.sp, color = cs.onSurfaceVariant)
                    Text(
                        d.band.inviteCode, fontSize = 26.sp, fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace, letterSpacing = 3.sp, color = cs.primary,
                        modifier = Modifier.testTag("band_invite_code"),
                    )
                }
                TextButton(onClick = {
                    ctx.getSystemService(ClipboardManager::class.java)
                        .setPrimaryClip(ClipData.newPlainText(tr("ROCKY 초대 코드", "ROCKY invite code"), d.band.inviteCode))
                    Toast.makeText(ctx, tr("초대 코드를 복사했어요", "Invite code copied"), Toast.LENGTH_SHORT).show()
                }) { Text(tr("복사", "Copy")) }
            }

            Spacer(Modifier.height(28.dp))
            SectionTitle(tr("멤버", "Members"), d.members.size)
            d.members.forEach { m ->
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        Modifier.size(42.dp).clip(CircleShape).background(cs.surface),
                        contentAlignment = Alignment.Center,
                    ) { InstrumentIcon(m.instrument, cs.primary, size = 24.dp) }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(m.nickname, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            if (m.userId == user.id) Tag(tr("나", "Me"), cs.primary)
                            if (m.isOwner) Tag(tr("방장", "Leader"), cs.secondary)
                        }
                        Text(Demo.kor(m.instrument), fontSize = 13.sp, color = cs.onSurfaceVariant)
                    }
                }
            }

            Spacer(Modifier.height(24.dp))
            SectionTitle(tr("공유된 악보", "Shared scores"), d.scores.size)
            if (d.scores.isEmpty()) {
                Text(
                    tr("공유된 악보가 없어요.", "No shared scores."),
                    color = cs.onSurfaceVariant, fontSize = 14.sp, modifier = Modifier.padding(vertical = 12.dp),
                )
            }
            d.scores.forEach { s ->
                Column(
                    Modifier.fillMaxWidth()
                        .padding(vertical = 6.dp)
                        .card(RoundedCornerShape(16.dp), cs)
                        .clickable { onOpenScore(s.work, myPart) }
                        .padding(16.dp)
                        .testTag("band_score_${s.id}"),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(s.work.title, fontWeight = FontWeight.Bold, fontSize = 16.sp, modifier = Modifier.weight(1f))
                        // 공유한 사람과 방장은 악보 이름을 바꿀 수 있다.
                        if (s.sharedById == user.id || isOwner) {
                            Text(
                                tr("이름 수정", "Rename"), fontSize = 12.sp, color = cs.primary,
                                modifier = Modifier.clip(RoundedCornerShape(8.dp)).clickable { renamingScore = s }
                                    .padding(horizontal = 6.dp, vertical = 4.dp).testTag("score_rename_${s.id}"),
                            )
                        }
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(
                        tr("${s.sharedByName}님이 공유 · ${DATE.format(Date(s.sharedAt))}", "Shared by ${s.sharedByName} · ${DATE.format(Date(s.sharedAt))}"),
                        fontSize = 13.sp, color = cs.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        s.work.instruments.forEach { inst ->
                            val mine = inst == myPart
                            Text(
                                (if (mine) tr("내 파트 · ", "Mine · ") else "") + Demo.label(inst, s.work.instruments),
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
                Text(tr("밴드 나가기", "Leave band"), color = cs.error)
            }
            Spacer(Modifier.height(8.dp))
        }
    }

    if (renamingBand && d != null) {
        TextInputDialog(
            title = tr("밴드 이름 수정", "Rename band"), initial = d.band.name, label = tr("밴드 이름", "Band name"), maxLength = BandRules.NAME_MAX,
            emoji = true, validate = BandRules::validateName,
            onDismiss = { renamingBand = false },
            onConfirm = { name ->
                scope.launch {
                    when (val r = repo.rename(user, d.band.id, name)) {
                        is BandResult.Success -> { renamingBand = false; version++ }
                        is BandResult.Failure -> Toast.makeText(ctx, r.message, Toast.LENGTH_SHORT).show()
                    }
                }
            },
        )
    }
    renamingScore?.let { s ->
        TextInputDialog(
            title = tr("악보 이름 수정", "Rename score"), initial = s.work.title, label = tr("악보 이름", "Score name"), maxLength = 60,
            onDismiss = { renamingScore = null },
            onConfirm = { t ->
                scope.launch {
                    if (repo.renameScore(user, bandId, s.id, t)) { renamingScore = null; version++ }
                    else Toast.makeText(ctx, tr("이름을 바꿀 수 없어요", "Couldn't rename"), Toast.LENGTH_SHORT).show()
                }
            },
        )
    }

    if (confirmLeave && d != null) {
        AlertDialog(
            onDismissRequest = { confirmLeave = false },
            confirmButton = {
                TextButton(onClick = {
                    confirmLeave = false
                    scope.launch {
                        repo.leave(user, d.band.id)
                        Toast.makeText(ctx, tr("'${d.band.name}'에서 나왔어요", "You left '${d.band.name}'"), Toast.LENGTH_SHORT).show()
                        onLeft()
                    }
                }, modifier = Modifier.testTag("band_leave_confirm")) { Text(tr("나가기", "Leave"), color = cs.error) }
            },
            dismissButton = { TextButton(onClick = { confirmLeave = false }) { Text(tr("취소", "Cancel")) } },
            title = { Text(tr("밴드에서 나갈까요?", "Leave this band?")) },
            text = {
                Text(
                    if (d.members.size <= 1) tr("마지막 멤버라서 밴드와 악보가 모두 지워져요.", "You're the last member. The band and its scores will be deleted.")
                    else tr("공유한 악보는 남아요. 초대 코드로 다시 들어올 수 있어요.", "Your shared scores stay. Rejoin with the code.")
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

    Page(tr("밴드에 공유", "Share with a band"), onBack) {
        Text(tr("어느 밴드에\n공유할까요?", "Which band\ngets this score?"), fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp)
        Spacer(Modifier.height(6.dp))
        Text(work.title, color = cs.onSurfaceVariant, maxLines = 1)
        Spacer(Modifier.height(24.dp))
        val list = bands
        when {
            list == null -> Loading()
            list.isEmpty() -> {
                Text(tr("아직 참여한 밴드가 없어요.", "You're not in a band yet."), color = cs.onSurfaceVariant)
                Spacer(Modifier.height(16.dp))
                OutlinedButton(shape = ButtonShape, onClick = onAddBand, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                    Text(tr("밴드 만들기 · 참여하기", "Create or join a band"))
                }
            }
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(list, key = { it.band.id }) { s ->
                    Row(
                        Modifier.fillMaxWidth()
                            .card(RoundedCornerShape(16.dp), cs)
                            .clickable {
                                scope.launch {
                                    val added = repo.share(user, s.band.id, work)
                                    Toast.makeText(
                                        ctx,
                                        if (added) tr("'${s.band.name}'에 공유했어요", "Shared with '${s.band.name}'")
                                        else tr("이미 '${s.band.name}'에 공유된 악보예요", "Already shared with '${s.band.name}'"),
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
                            Text(s.band.name, fontWeight = FontWeight.Bold, fontSize = 17.sp, maxLines = 1)
                            Text(tr("멤버 ${s.memberCount}명", "${s.memberCount} members"), fontSize = 13.sp, color = cs.onSurfaceVariant)
                        }
                        Text(tr("공유", "Share"), color = cs.primary, fontWeight = FontWeight.Bold)
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

    Page(tr("악보 공유", "Share a score"), onBack) {
        Text(tr("보관함에서 악보를\n골라주세요", "Pick a score\nfrom your library"), fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 36.sp)
        Spacer(Modifier.height(24.dp))
        if (works.isEmpty()) {
            Text(
                tr("보관함이 비어 있어요.", "Your library is empty."),
                color = cs.onSurfaceVariant,
            )
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(works, key = { it.id }) { w ->
                Column(
                    Modifier.fillMaxWidth()
                        .card(RoundedCornerShape(16.dp), cs)
                        .clickable {
                            scope.launch {
                                val added = repo.share(user, bandId, w)
                                Toast.makeText(
                                    ctx, if (added) tr("밴드에 공유했어요", "Shared with the band") else tr("이미 공유된 악보예요", "Already shared"), Toast.LENGTH_SHORT,
                                ).show()
                                onBack()
                            }
                        }
                        .padding(18.dp),
                ) {
                    Text(w.title, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        Demo.labels(w.instruments) + "   |   " + w.date,
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
    Row(
        Modifier
            .clip(RoundedCornerShape(10.dp))
            .background(cs.primary.copy(alpha = 0.14f))
            .padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(tr("내 파트  ", "Mine  "), fontSize = 13.sp, fontWeight = FontWeight.Bold, color = cs.primary)
        InstrumentIcon(inst, cs.primary, size = 16.dp)
        Text(" ${Demo.kor(inst)}", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = cs.primary)
    }
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
        val fg = if (on) cs.onPrimary else cs.onSurface
        InstrumentIcon(inst, fg, size = 26.dp)
        Spacer(Modifier.height(2.dp))
        Text(Demo.kor(inst), fontSize = 12.sp, fontWeight = FontWeight.Bold, color = fg, maxLines = 1)
    }
}

@Composable
private fun Segmented(left: String, right: String, rightOn: Boolean, onChange: (Boolean) -> Unit) {
    val cs = MaterialTheme.colorScheme
    Row(
        Modifier.fillMaxWidth().card(RoundedCornerShape(14.dp), cs).padding(4.dp),
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
