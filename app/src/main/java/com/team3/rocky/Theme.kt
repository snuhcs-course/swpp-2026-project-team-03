package com.team3.rocky

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// ---------- 테마 (색상만 있어서 커버리지 측정에서 제외) ----------
// DemoData.kt에 있던 것을 그대로 옮겼습니다. 앱 모양은 바뀌지 않습니다.
private val RockyColors = darkColorScheme(
    primary = Color(0xFFFF7A3D),
    onPrimary = Color(0xFF1A1A1A),
    secondary = Color(0xFFFFC857),
    onSecondary = Color(0xFF1A1A1A),
    background = Color(0xFF111114),
    onBackground = Color(0xFFF2F2F2),
    surface = Color(0xFF1C1C22),
    onSurface = Color(0xFFF2F2F2),
    surfaceVariant = Color(0xFF2A2A33),
    onSurfaceVariant = Color(0xFFB4B4C0),
)

@Composable
fun RockyTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = RockyColors, content = content)
}
