// AI-generated with Claude Code, 2026-11-09
package com.team3.rocky

import android.widget.Toast
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// 무대는 화면 모드(다크/라이트)와 상관없이 늘 어두운 무대로 그린다.
private val Orange = Color(0xFFFF6B2C)
private val OnOrange = Color(0xFF1A1A1A)
private val SpotOff = Color(0xFF24242C)
private val SpotOffLine = Color(0xFF34343E)
private val LabelOn = Color(0xFFF2F2F2)
private val LabelOff = Color(0xFFB4B4C0)
private val LabelLocked = Color(0xFF5E5E6A)

/** 무대 위 자리 하나. [x]는 무대 너비에 대한 비율, [y]는 원 가운데까지의 높이. */
private class StageSpot(val key: String, val icon: String, val x: Float, val y: Dp, val size: Dp)

// 실제 밴드 무대처럼: 뒷줄 베이스·드럼·피아노, 앞줄 기타 1·기타 2. 드럼만 조금 크게.
private val SPOTS = listOf(
    StageSpot("bass", "bass", 0.18f, 104.dp, 74.dp),
    StageSpot("drums", "drums", 0.50f, 92.dp, 88.dp),
    StageSpot("piano", "piano", 0.82f, 104.dp, 74.dp),
    StageSpot("guitar", "guitar", 0.31f, 262.dp, 78.dp),
    StageSpot(Demo.GUITAR2, "guitar", 0.69f, 262.dp, 78.dp),
)
private val STAGE_HEIGHT = 372.dp

/** 아래 요약에 쓰는 순서 (기타가 맨 끝에 오지 않게) */
private val SUMMARY_ORDER = listOf("drums", "guitar", Demo.GUITAR2, "bass", "piano")

/**
 * 1단계: 우리 밴드 악기 고르기. 무대 위 악기 5개(기타는 2대까지)를 눌러 켜고 끈다.
 * 기타 2는 기타 1을 고른 뒤에만 고를 수 있다.
 */
@Composable
fun BandStageScreen(
    lineup: Set<String>,
    onChange: (Set<String>) -> Unit,
    onBack: () -> Unit,
    onNext: () -> Unit,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val guitars = Demo.guitarCount(lineup)

    fun tap(key: String) {
        when (key) {
            "guitar" -> onChange(Demo.setGuitarCount(lineup, if (guitars > 0) 0 else 1))
            Demo.GUITAR2 -> when (guitars) {
                0 -> Toast.makeText(ctx, tr("기타 1을 먼저 골라 주세요", "Pick Guitar 1 first"), Toast.LENGTH_SHORT).show()
                1 -> onChange(Demo.setGuitarCount(lineup, 2))
                else -> onChange(Demo.setGuitarCount(lineup, 1))
            }
            else -> onChange(Demo.toggleLineup(lineup, key))
        }
    }

    val picked = SUMMARY_ORDER.filter { it in lineup }
    val names = picked.map { spotLabel(it) }

    Page(tr("1 / 3단계", "Step 1 of 3"), onBack, actions = { StepBars(1) }, bottom = {
        Column {
            // 고른 악기 요약
            Row(
                Modifier.fillMaxWidth().card(RoundedCornerShape(16.dp), cs)
                    .padding(horizontal = 16.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(tr("우리 밴드", "Your band"), fontSize = 12.sp, fontWeight = FontWeight.Bold, color = cs.onSurfaceVariant)
                    Spacer(Modifier.height(4.dp))
                    if (names.isEmpty()) {
                        Text(tr("아직 고른 악기가 없어요", "Nothing picked yet"), fontSize = 14.sp, color = cs.onSurfaceVariant, maxLines = 1)
                    } else {
                        Text(names.joinToString(" · "), fontSize = 16.sp, fontWeight = FontWeight.Bold, color = cs.primary,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Text("${names.size}", fontSize = 22.sp, fontWeight = FontWeight.Black)
                Text(tr("개", ""), fontSize = 13.sp, fontWeight = FontWeight.Bold, color = cs.onSurfaceVariant)
            }
            Spacer(Modifier.height(12.dp))
            Button(shape = ButtonShape,
                onClick = onNext, enabled = lineup.isNotEmpty(),
                modifier = Modifier.fillMaxWidth().height(56.dp),
            ) { Text(tr("다음", "Next"), fontSize = 17.sp, fontWeight = FontWeight.Bold) }
        }
    }) {
        Column(Modifier.verticalScroll(rememberScrollState())) {
            Text(tr("우리 밴드에\n어떤 악기가 있나요?", "What instruments\nare in your band?"),
                fontSize = 26.sp, fontWeight = FontWeight.Bold, lineHeight = 34.sp)
            Spacer(Modifier.height(6.dp))
            Text(tr("무대에서 눌러 고르세요 · 기타는 2대까지", "Tap them on stage · up to 2 guitars"),
                fontSize = 14.sp, color = cs.onSurfaceVariant)
            Spacer(Modifier.height(18.dp))
            Stage(lineup, guitars, onTap = { tap(it) })
            Spacer(Modifier.height(16.dp))
        }
    }
}

private fun spotLabel(key: String) = when (key) {
    "guitar" -> tr("기타 1", "Guitar 1")
    Demo.GUITAR2 -> tr("기타 2", "Guitar 2")
    else -> Demo.kor(key)
}

@Composable
private fun Stage(lineup: Set<String>, guitars: Int, onTap: (String) -> Unit) {
    BoxWithConstraints(
        Modifier.fillMaxWidth().height(STAGE_HEIGHT).clip(RoundedCornerShape(24.dp))
            .background(Color(0xFF16161B)),
    ) {
        val stageWidth = maxWidth
        // 무대 배경: 위에서 퍼지는 빛, 바닥, 조명 레일, 고른 악기 위 조명
        Canvas(Modifier.fillMaxSize()) {
            val w = size.width
            val h = size.height
            drawRect(Brush.radialGradient(listOf(Color(0xFF26262F), Color(0xFF16161B)), center = Offset(w / 2, 0f), radius = w * 0.8f))
            // 바닥 (넓은 타원의 윗부분)
            val floorTop = h - 170.dp.toPx()
            drawOval(
                Brush.verticalGradient(listOf(Color(0xFF22222A), Color(0xFF1A1A20)), startY = floorTop, endY = h),
                topLeft = Offset(-w * 0.1f, floorTop), size = Size(w * 1.2f, 260.dp.toPx()),
            )
            drawOval(
                Color(0xFF2E2E38), topLeft = Offset(-w * 0.1f, floorTop), size = Size(w * 1.2f, 260.dp.toPx()),
                style = Stroke(1.dp.toPx()),
            )
            // 조명 레일
            val dash = 18.dp.toPx(); val gap = 8.dp.toPx()
            var x = 0f
            while (x < w) { drawRect(Color(0xCC2E2E38), Offset(x, 0f), Size(dash, 6.dp.toPx())); x += dash + gap }
            // 고른 악기 위 조명과 바닥 빛
            SPOTS.filter { it.key in lineup }.forEach { s ->
                val cx = w * s.x
                val cy = s.y.toPx()
                val half = 44.dp.toPx()
                val beam = Path().apply {
                    moveTo(cx - half * 0.08f, 0f); lineTo(cx + half * 0.08f, 0f)
                    lineTo(cx + half, cy); lineTo(cx - half, cy); close()
                }
                drawPath(beam, Brush.verticalGradient(
                    listOf(Orange.copy(alpha = 0f), Orange.copy(alpha = 0.06f), Orange.copy(alpha = 0.16f)), startY = 0f, endY = cy,
                ))
                val poolW = 112.dp.toPx(); val poolH = 34.dp.toPx()
                val poolTop = cy + s.size.toPx() / 2 - 14.dp.toPx()
                drawOval(
                    Brush.radialGradient(listOf(Orange.copy(alpha = 0.45f), Orange.copy(alpha = 0f)),
                        center = Offset(cx, poolTop + poolH / 2), radius = poolW / 2),
                    topLeft = Offset(cx - poolW / 2, poolTop), size = Size(poolW, poolH),
                )
            }
        }
        SPOTS.forEach { s ->
            val state = when {
                s.key in lineup -> SpotState.On
                s.key == Demo.GUITAR2 && guitars == 0 -> SpotState.Locked
                else -> SpotState.Off
            }
            val labelWidth = 104.dp
            Box(
                Modifier.offset(x = stageWidth * s.x - labelWidth / 2, y = s.y - s.size / 2).width(labelWidth),
                contentAlignment = Alignment.TopCenter,
            ) { InstrumentSpot(s, state) { onTap(s.key) } }
        }
    }
}

private enum class SpotState { On, Off, Locked }

@Composable
private fun InstrumentSpot(spot: StageSpot, state: SpotState, onClick: () -> Unit) {
    val on = state == SpotState.On
    val fill by animateColorAsState(if (on) Orange else if (state == SpotState.Locked) Color.Transparent else SpotOff, label = "fill")
    val iconColor by animateColorAsState(if (on) OnOrange else if (state == SpotState.Locked) LabelLocked else LabelOff, label = "icon")
    val label = spotLabel(spot.key)
    Column(
        Modifier.clip(RoundedCornerShape(16.dp)).clickable(onClick = onClick)
            .semantics {
                role = Role.Checkbox
                selected = on
                contentDescription = label + when (state) {
                    SpotState.On -> tr(", 선택됨", ", selected")
                    SpotState.Locked -> tr(", 기타 1을 먼저 골라 주세요", ", pick Guitar 1 first")
                    SpotState.Off -> ""
                }
            },
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(Modifier.size(spot.size)) {
            Box(
                Modifier.fillMaxSize().clip(CircleShape).background(fill)
                    .then(
                        when (state) {
                            SpotState.On -> Modifier.border(4.dp, Orange.copy(alpha = 0.25f), CircleShape)
                            SpotState.Off -> Modifier.border(1.5.dp, SpotOffLine, CircleShape)
                            SpotState.Locked -> Modifier
                        },
                    ),
                contentAlignment = Alignment.Center,
            ) { InstrumentIcon(spot.icon, iconColor, size = spot.size * 0.52f) }
            if (state == SpotState.Locked) {
                // 아직 고를 수 없는 자리: 점선 원
                Canvas(Modifier.fillMaxSize()) {
                    val stroke = 2.dp.toPx()
                    drawCircle(
                        Color(0xFF3A3A45), radius = size.minDimension / 2 - stroke / 2,
                        style = Stroke(stroke, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 5.dp.toPx()))),
                    )
                }
            }
            if (on) {
                Box(
                    Modifier.align(Alignment.TopEnd).offset(x = 2.dp, y = (-2).dp).size(22.dp)
                        .clip(CircleShape).background(LabelOn),
                    contentAlignment = Alignment.Center,
                ) { Text("✓", fontSize = 13.sp, fontWeight = FontWeight.Black, color = OnOrange) }
            }
        }
        Spacer(Modifier.height(7.dp))
        Text(
            label, fontSize = 14.sp, maxLines = 1,
            fontWeight = if (on) FontWeight.ExtraBold else FontWeight.SemiBold,
            color = when (state) { SpotState.On -> LabelOn; SpotState.Off -> LabelOff; SpotState.Locked -> LabelLocked },
        )
        if (state == SpotState.Locked) {
            Text(tr("기타 1 먼저", "Guitar 1 first"), fontSize = 11.sp, color = LabelLocked, maxLines = 1)
        }
    }
}

/** 오른쪽 위 단계 막대. [current]번째까지 주황. */
@Composable
fun StepBars(current: Int, total: Int = 3) {
    val cs = MaterialTheme.colorScheme
    Row(Modifier.padding(end = 16.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        repeat(total) { i ->
            Box(
                Modifier.width(22.dp).height(4.dp).clip(RoundedCornerShape(2.dp))
                    .background(if (i < current) cs.primary else cs.surfaceVariant),
            )
        }
    }
}
