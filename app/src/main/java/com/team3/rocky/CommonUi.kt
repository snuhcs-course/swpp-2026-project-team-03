package com.team3.rocky

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.graphics.Shape
import androidx.compose.material3.Typography
import androidx.compose.material3.ColorScheme
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.union
import androidx.compose.foundation.layout.tappableElement
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.io.File

// ---------- 테마 ----------
// 시안 A '스튜디오': 무채색 바탕 + 절제된 주황, 얇은 1px 테두리, 넉넉한 여백.
private val DarkColors = darkColorScheme(
    primary = Color(0xFFFF6B2C),
    onPrimary = Color(0xFF111111),
    secondary = Color(0xFFFFC857),
    onSecondary = Color(0xFF111111),
    background = Color(0xFF0E0E10),
    onBackground = Color(0xFFF4F4F5),
    surface = Color(0xFF18181B),
    onSurface = Color(0xFFF4F4F5),
    surfaceVariant = Color(0xFF26262B),
    onSurfaceVariant = Color(0xFF9B9BA3),
    surfaceContainer = Color(0xFF0E0E10),
    outlineVariant = Color(0xFF26262B),
)

private val LightColors = lightColorScheme(
    primary = Color(0xFFF0601F),
    onPrimary = Color(0xFFFFFFFF),
    secondary = Color(0xFFB7791F),
    onSecondary = Color(0xFFFFFFFF),
    background = Color(0xFFF7F7F8),
    onBackground = Color(0xFF18181B),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF18181B),
    surfaceVariant = Color(0xFFEDEDF0),
    onSurfaceVariant = Color(0xFF6B6B74),
    surfaceContainer = Color(0xFFF7F7F8),
    outlineVariant = Color(0xFFE4E4E7),
)

/** 앱 전체 글꼴. 한글이 또렷한 Pretendard(SIL OFL 1.1). */
val Pretendard = FontFamily(
    Font(R.font.pretendard_regular, FontWeight.Normal),
    Font(R.font.pretendard_medium, FontWeight.Medium),
    Font(R.font.pretendard_semibold, FontWeight.SemiBold),
    Font(R.font.pretendard_bold, FontWeight.Bold),
    Font(R.font.pretendard_extrabold, FontWeight.ExtraBold),
    Font(R.font.pretendard_extrabold, FontWeight.Black),
)

/** 모든 글자 스타일에 Pretendard를 쓰고, 큰 제목은 자간을 살짝 좁힌다. */
private val RockyTypography = Typography().let { t ->
    fun TextStyle.p(tight: Boolean = false) =
        copy(fontFamily = Pretendard, letterSpacing = if (tight) (-0.4).sp else letterSpacing)
    t.copy(
        displayLarge = t.displayLarge.p(true), displayMedium = t.displayMedium.p(true), displaySmall = t.displaySmall.p(true),
        headlineLarge = t.headlineLarge.p(true), headlineMedium = t.headlineMedium.p(true), headlineSmall = t.headlineSmall.p(true),
        titleLarge = t.titleLarge.p(true), titleMedium = t.titleMedium.p(), titleSmall = t.titleSmall.p(),
        bodyLarge = t.bodyLarge.p(), bodyMedium = t.bodyMedium.p(), bodySmall = t.bodySmall.p(),
        labelLarge = t.labelLarge.p(), labelMedium = t.labelMedium.p(), labelSmall = t.labelSmall.p(),
    )
}

@Composable
fun RockyTheme(dark: Boolean = AppSettings.dark, content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) DarkColors else LightColors, typography = RockyTypography, content = content)
}

/** 카드 바탕: 둥근 모서리 + 면 색 + 얇은 1px 테두리 (시안 A). */
fun Modifier.card(shape: Shape, cs: ColorScheme, bg: Color = cs.surface, line: Color = cs.outlineVariant): Modifier =
    clip(shape).background(bg).border(1.dp, line, shape)

// ---------- 악기 아이콘 ----------
/**
 * 한 가지 색으로 그리는 악기 아이콘. 이모지와 달리 색을 바꿀 수 있어서,
 * 선택한 칸에서는 글자와 같은 색으로 바뀐다.
 * 피아노·기타·베이스·보컬은 24칸 격자의 SVG 선(path)으로 그린다.
 */
@Composable
fun InstrumentIcon(inst: String, color: Color, size: Dp = 32.dp, modifier: Modifier = Modifier) {
    Canvas(modifier.size(size)) {
        val u = this.size.minDimension / 24f       // 24칸 격자 기준
        val key = Demo.assetBase(inst)
        val spec = InstrumentIcons.specs[key]
        if (spec == null) {
            if (key == "drums") drums(u, color, Stroke(width = 1.8f * u, cap = StrokeCap.Round))
            else drawCircle(color, radius = 6 * u, style = Stroke(1.8f * u))
            return@Canvas
        }
        withTransform({
            scale(u, u, pivot = Offset.Zero)
            rotate(spec.rotation, pivot = Offset(12f, 12f))
        }) {
            // 마이크 머리의 격자는 가늘게 그려야 작은 크기에서 뭉개지지 않는다.
            spec.stroke.forEachIndexed { i, path ->
                val w = if (key == Demo.VOCAL && i == 1) 1.2f else 1.8f
                drawPath(path, color, style = Stroke(width = w, cap = StrokeCap.Round, join = StrokeJoin.Round))
            }
            spec.fill.forEach { drawPath(it, color) }
        }
    }
}

private class IconSpec(stroke: List<String>, fill: List<String>, val rotation: Float) {
    val stroke = stroke.map { PathParser().parsePathString(it).toPath() }
    val fill = fill.map { PathParser().parsePathString(it).toPath() }
}

/** 아이콘 선 모음. 기타·베이스는 세워서 그린 뒤 45도 기울인다. */
private object InstrumentIcons {
    val specs = mapOf(
        "piano" to IconSpec(listOf("M3.5 5h17a1.5 1.5 0 0 1 1.5 1.5v11a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 2 17.5v-11A1.5 1.5 0 0 1 3.5 5z", "M6 12.5V19 M10 12.5V19 M14 5V19 M18 12.5V19"), listOf("M4.8 5h2.4v7.5H4.8z M8.8 5h2.4v7.5H8.8z M16.8 5h2.4v7.5h-2.4z"), 0.0f),
        "guitar" to IconSpec(listOf("M12 8.4C14.4 8.4 15.6 10 15.6 11.8C15.6 13 14.8 13.8 14.6 14.6C16 15.2 16.8 16.6 16.8 18.2C16.8 21 14.6 23 12 23C9.4 23 7.2 21 7.2 18.2C7.2 16.6 8 15.2 9.4 14.6C9.2 13.8 8.4 13 8.4 11.8C8.4 10 9.6 8.4 12 8.4Z", "M12 8.4V3", "M10.6 19.8h2.8"), listOf("M10.6 0.8h2.8v3.4h-2.8z", "M12 13.6m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0"), 45.0f),
        "bass" to IconSpec(listOf("M8.6 11.2C9.4 11.2 10 12.2 10.4 13.4L13.6 13.4C13.9 12.6 14.4 12.2 15 12.2C15.8 12.2 16.2 13 16 13.8C15.8 14.8 15.6 15.6 16.4 16.6C17.4 17.8 17.4 20.4 16 21.8C14.4 23.4 9.6 23.4 8 21.8C6.6 20.4 6.6 17.8 7.6 16.6C8.4 15.6 8 14.6 7.6 13.4C7.2 12.2 7.8 11.2 8.6 11.2Z", "M12 13.4V1.6", "M10.4 17.4h3.2 M10.6 20.2h2.8"), listOf("M10.2 1.6m-0.9 0a0.9 0.9 0 1 0 1.8 0a0.9 0.9 0 1 0-1.8 0", "M10.2 4.2m-0.9 0a0.9 0.9 0 1 0 1.8 0a0.9 0.9 0 1 0-1.8 0", "M13.8 1.6m-0.9 0a0.9 0.9 0 1 0 1.8 0a0.9 0.9 0 1 0-1.8 0", "M13.8 4.2m-0.9 0a0.9 0.9 0 1 0 1.8 0a0.9 0.9 0 1 0-1.8 0"), 45.0f),
        "vocal" to IconSpec(listOf("M15.5 8.5m-4.2 0a4.2 4.2 0 1 0 8.4 0a4.2 4.2 0 1 0-8.4 0", "M14.5 5.4l4.1 4.1 M12.4 7.5l4.1 4.1 M14.5 11.6l4.1-4.1 M12.4 9.5l4.1-4.1", "M11.6 10.4L4.3 18.3a1 1 0 0 0 1.4 1.4L13.6 12.4"), listOf(), 0.0f),
    )
}

private fun DrawScope.drums(u: Float, c: Color, s: Stroke) {
    drawOval(c, Offset(3 * u, 8 * u), Size(18 * u, 5 * u), style = s)
    drawLine(c, Offset(3 * u, 10.5f * u), Offset(3 * u, 17 * u), s.width, StrokeCap.Round)
    drawLine(c, Offset(21 * u, 10.5f * u), Offset(21 * u, 17 * u), s.width, StrokeCap.Round)
    drawArc(c, 0f, 180f, false, Offset(3 * u, 14.5f * u), Size(18 * u, 5 * u), style = s)
    drawLine(c, Offset(7 * u, 2.5f * u), Offset(11 * u, 9.5f * u), s.width, StrokeCap.Round)
    drawLine(c, Offset(17 * u, 2.5f * u), Offset(13 * u, 9.5f * u), s.width, StrokeCap.Round)
}

// ---------- 프로필 사진 ----------
/** 프로필 사진은 앱 안의 파일(files/profile_<회원 id>.jpg)로 저장한다. 서버가 생기면 서버로 옮긴다. */
object ProfileStore {
    private fun file(ctx: Context, userId: Long) = File(ctx.filesDir, "profile_$userId.jpg")

    fun save(ctx: Context, userId: Long, uri: Uri): Boolean = try {
        val bmp = decodeSampled(ctx, uri, 512) ?: error("decode")
        file(ctx, userId).outputStream().use { bmp.compress(Bitmap.CompressFormat.JPEG, 90, it) }
        true
    } catch (_: Exception) {
        false
    }

    fun remove(ctx: Context, userId: Long) { file(ctx, userId).delete() }

    fun load(ctx: Context, userId: Long): ImageBitmap? =
        file(ctx, userId).takeIf { it.exists() }?.let { BitmapFactory.decodeFile(it.absolutePath)?.asImageBitmap() }

    /** 고른 사진을 미리 보여줄 때 쓴다. */
    fun preview(ctx: Context, uri: Uri): ImageBitmap? = decodeSampled(ctx, uri, 512)?.asImageBitmap()

    private fun decodeSampled(ctx: Context, uri: Uri, maxSide: Int): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        ctx.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
        var sample = 1
        while (bounds.outWidth / (sample * 2) >= maxSide && bounds.outHeight / (sample * 2) >= maxSide) sample *= 2
        val opts = BitmapFactory.Options().apply { inSampleSize = sample }
        return ctx.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, opts) }
    }
}

/** 둥근 프로필 사진. 사진이 없으면 닉네임 첫 글자를 보여준다. */
@Composable
fun Avatar(image: ImageBitmap?, nickname: String, size: Dp, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    Box(
        modifier.size(size).clip(CircleShape).background(cs.primary.copy(alpha = 0.18f)),
        contentAlignment = Alignment.Center,
    ) {
        if (image != null) {
            Image(image, contentDescription = tr("프로필 사진", "Profile photo"), contentScale = ContentScale.Crop, modifier = Modifier.size(size))
        } else {
            Text(
                nickname.trim().take(1).ifEmpty { "?" },
                fontSize = (size.value * 0.42f).sp, fontWeight = FontWeight.Bold, color = cs.primary,
            )
        }
    }
}

/** 밴드 이름 등에 바로 넣을 수 있는 이모티콘. 키보드에 이모티콘이 없는 폰에서도 넣을 수 있게 한다. */
val QUICK_EMOJI = listOf("🎸", "🥁", "🎹", "🎤", "🎵", "🔥", "⭐", "🤘", "💜", "🌙")


/**
 * 버튼 여러 개를 한 줄에 놓을 때 쓰는 안쪽 여백. 기본값(좌우 24dp)이면 "보관함에 저장"처럼
 * 글자가 잘려서 좌우를 줄인다.
 */
val TightButtonPadding = PaddingValues(horizontal = 6.dp, vertical = 8.dp)

/**
 * 화면 맨 아래 버튼·탭이 피해야 하는 영역: 갤럭시의 홈·뒤로 버튼 줄(내비게이션 바)과
 * 제스처 막대처럼 눌러지는 시스템 영역. 이미 다른 곳에서 비켜 줬으면 다시 더하지 않는다.
 */
val BottomSystemBars: WindowInsets
    get() = WindowInsets.navigationBars.union(WindowInsets.tappableElement)
        .only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal)

/** 주요 버튼 모양 (시안 A): 알약 대신 살짝 둥근 사각형. */
val ButtonShape = RoundedCornerShape(14.dp)
