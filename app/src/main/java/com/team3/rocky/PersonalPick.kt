// AI-generated with Claude Code, 2026-11-13
package com.team3.rocky

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 개인 연습용 1단계: 내가 연습할 악기 고르기 (2x2 칸, **한 종류만**. 기타는 1~2대).
 * 고른 악기의 악보만 만든다. 원곡에 없는 악기는 밴드 합주용처럼 AI가 만든다.
 * 기타는 원곡 기타 대수에 맞춰 1~2대를 고르고, 아래에 대수에 따른 안내를 보여준다.
 * 두 종류 이상이 필요하면 밴드 합주용을 쓰라고 안내한다.
 */
@Composable
fun PersonalPickScreen(
    picked: Set<String>,
    onToggle: (String) -> Unit,
    onGuitars: (Int) -> Unit,
    onBack: () -> Unit,
    onNext: () -> Unit,
    /** 제목 위에 보여줄 안내 (기타 대수 바꿔서 다시 만들 때). */
    notice: String? = null,
    /** 이 구성으로는 만들 수 없는 이유. 있으면 '다음'을 막고 아래에 보여준다. */
    blocked: String? = null,
) {
    val cs = MaterialTheme.colorScheme
    val guitars = Demo.guitarCount(picked)
    Page(tr("1 / 2단계", "Step 1 of 2"), onBack, actions = { StepBars(1) }, bottom = {
        Column {
            if (blocked != null) {
                Text(blocked, fontSize = 13.sp, color = cs.error, lineHeight = 18.sp)
                Spacer(Modifier.height(8.dp))
            }
            Button(shape = ButtonShape,
                onClick = onNext, enabled = picked.isNotEmpty() && blocked == null,
                modifier = Modifier.fillMaxWidth().height(56.dp),
            ) { Text(if (picked.isEmpty()) tr("악기를 골라 주세요", "Pick an instrument") else tr("다음", "Next"), fontSize = 17.sp, fontWeight = FontWeight.Bold) }
        }
    }) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            if (notice != null) {
                InfoNote(notice, strong = true)
                Spacer(Modifier.height(14.dp))
            }
            Text(tr("어떤 악기를 연습하나요?", "Which instruments are you practicing?"),
                fontSize = 26.sp, fontWeight = FontWeight.Bold, lineHeight = 34.sp)
            Spacer(Modifier.height(6.dp))
            Text(tr("연습할 악기 하나를 골라 주세요. 그 악기의 악보만 만들어요.", "Pick the one instrument you practice. We make just its score."),
                fontSize = 14.sp, color = cs.onSurfaceVariant, lineHeight = 20.sp)
            Spacer(Modifier.height(20.dp))
            Demo.INSTRUMENTS.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { inst ->
                        val count = if (inst == "guitar") guitars else if (inst in picked) 1 else 0
                        InstrumentTile(inst, count, Modifier.weight(1f), onCount = if (inst == "guitar") onGuitars else null) {
                            onToggle(inst)
                        }
                    }
                }
                Spacer(Modifier.height(12.dp))
            }
            // 기타 대수에 따른 안내. 원곡 기타 대수와 맞추면 가장 치기 좋은 악보가 나온다.
            Demo.guitarNote(guitars)?.let { InfoNote(it); Spacer(Modifier.height(8.dp)) }
            // 서버가 mode=personal 이면 고른 악기 stem(+드럼)만 먼저 채보해 보고, 곡에 있으면 그것만 채보한다.
            // 기타 2대는 두 번째 기타를 AI로 만들 수 있어 처음부터 모두 채보하므로 이 문장을 띄우지 않는다.
            if (guitars != 2) {
                Text(
                    tr("원곡에 있는 악기는 밴드용보다 채보시간이 단축돼요.",
                        "If the song already has this instrument, it's transcribed faster than in band mode."),
                    fontSize = 13.sp, color = cs.onSurfaceVariant, lineHeight = 18.sp,
                )
                Spacer(Modifier.height(4.dp))
            }
            Text(
                tr("두 종류 이상의 악기 악보가 필요하면 홈에서 '밴드 합주용'으로 만들어 주세요.",
                    "Need scores for more than one instrument? Use 'Band rehearsal' on Home."),
                fontSize = 13.sp, color = cs.onSurfaceVariant, lineHeight = 18.sp,
            )
            Spacer(Modifier.height(16.dp))
        }
    }
}

/**
 * 악기 칸. 누르면 켜고 끈다.
 * [onCount]가 있으면(기타) 켜졌을 때 이름 옆에 − 숫자 + 버튼이 나와서 대수를 바꿀 수 있다.
 * [onBg]·[onFg]는 켜졌을 때 색 (기본 주황).
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
        modifier.height(132.dp)
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
        // 이름은 모든 칸에서 같은 자리. 기타는 같은 줄 오른쪽에 − 숫자 + (작은 폰에서도 잘리지 않게 숫자만).
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(Demo.kor(inst), fontSize = 18.sp, fontWeight = FontWeight.Bold, color = fg, maxLines = 1)
            Spacer(Modifier.weight(1f))
            if (onCount != null && on) {
                StepButton("−", enabled = count > 1, bg = onFg, fg = onBg) { onCount(count - 1) }
                Text("$count", fontSize = 16.sp, maxLines = 1, fontWeight = FontWeight.Bold, color = fg,
                    modifier = Modifier.padding(horizontal = 6.dp))
                StepButton("+", enabled = count < 2, bg = onFg, fg = onBg) { onCount(count + 1) }
            }
        }
    }
}

@Composable
private fun StepButton(text: String, enabled: Boolean, bg: Color, fg: Color, onClick: () -> Unit) {
    Box(
        Modifier.size(28.dp)
            .clip(androidx.compose.foundation.shape.CircleShape)
            .background(bg.copy(alpha = if (enabled) 1f else 0.35f))
            .clickable(enabled = enabled, onClick = onClick)
            .semantics { contentDescription = if (text == "+") tr("기타 늘리기", "More guitars") else tr("기타 줄이기", "Fewer guitars") },
        contentAlignment = Alignment.Center,
    ) {
        Text(text, fontSize = 17.sp, fontWeight = FontWeight.Bold, color = fg)
    }
}
