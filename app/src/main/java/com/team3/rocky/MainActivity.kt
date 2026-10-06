package com.team3.rocky

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        @Suppress("DEPRECATION")
        window.statusBarColor = 0xFF111114.toInt()
        setContent {
            RockyTheme {
                RockyApp()
            }
        }
    }
}
