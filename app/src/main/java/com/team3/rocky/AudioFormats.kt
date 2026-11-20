// AI-generated with Claude Code, 2026-11-20
package com.team3.rocky

/** 고를 수 있는 곡 파일 (Req&Spec NFR-01: MP3·WAV·FLAC·OGG). 파일 앱에서 이 형식만 보이게 한다. */
val PICK_TYPES = arrayOf(
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave",
    "audio/flac", "audio/x-flac", "audio/ogg", "application/ogg", "audio/vorbis",
)

/** 올릴 수 있는 곡 파일 확장자 (서버 `AUDIO_EXT`에 있는 것 중 앱이 받는 것). */
val AUDIO_EXTENSIONS = listOf("mp3", "wav", "flac", "ogg")

/** 파일 이름으로 올릴 수 있는 곡인지 본다. 대소문자는 가리지 않는다. */
fun isSupportedAudio(name: String): Boolean =
    name.contains('.') && name.substringAfterLast('.').lowercase() in AUDIO_EXTENSIONS
