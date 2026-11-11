// AI-generated with Claude Code, 2026-11-07
package com.team3.rocky

/** 앱에서 고를 수 있는 언어. [label]은 언어 고르기 칸에 그 언어로 보여준다. */
enum class Lang(val code: String, val label: String) {
    KO("ko", "한국어"),
    EN("en", "English"),
}

/**
 * 지금 고른 언어의 문구. 한국어와 영어를 나란히 적어 두면 어느 화면 문구인지 코드에서 바로 보인다.
 * AppSettings.lang은 Compose 상태라서 언어를 바꾸면 화면이 바로 다시 그려진다.
 */
fun tr(ko: String, en: String): String = if (AppSettings.lang == Lang.EN) en else ko

/** 영어에서 1개/여러 개를 다르게 쓸 때. "1 file" / "3 files" */
fun plural(n: Int, one: String, many: String) = if (n == 1) one else many
