package com.team3.rocky

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.LocalOverscrollFactory
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.core.view.WindowCompat
import com.team3.rocky.progress.ScoreJobs

class MainActivity : ComponentActivity() {
    // 앱을 보고 있는지. 안 보는 동안 악보 만들기가 멈추면 휴대폰 알림으로 알린다 (progress/JobNotifier).
    override fun onStart() { super.onStart(); ScoreJobs.appVisible = true }
    override fun onStop() { ScoreJobs.appVisible = false; super.onStop() }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        AppSettings.load(this)
        setContent {
            val dark = AppSettings.dark
            // 상태 표시줄 글자색을 화면 모드에 맞춘다.
            SideEffect {
                WindowCompat.getInsetsController(window, window.decorView).apply {
                    isAppearanceLightStatusBars = !dark
                    isAppearanceLightNavigationBars = !dark
                }
            }
            RockyTheme(dark) {
                // 화면 끝에서 더 당길 때 화면이 늘어나는 효과를 끈다.
                CompositionLocalProvider(LocalOverscrollFactory provides null) {
                    RockyApp()
                }
            }
        }
    }
}
