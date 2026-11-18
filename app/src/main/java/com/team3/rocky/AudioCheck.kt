package com.team3.rocky

import android.content.Context
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.net.Uri
import java.nio.ByteBuffer

/**
 * 곡을 고르자마자 폰에서 바로 확인한다 (서버까지 보내서 몇 분 기다린 뒤에 거절당하지 않게).
 * - 확장자만 MP3·WAV이고 실제로는 다른 파일이거나 깨진 파일 → [Broken]
 * - 30초 이하 → [TooShort] (서버 파이프라인도 30초 미만은 거절한다)
 */
object AudioCheck {
    const val MIN_SECONDS = 30

    sealed class Result {
        object Ok : Result()
        object Broken : Result()
        data class TooShort(val seconds: Int) : Result()
    }

    /** 오래 걸릴 수 있으니 IO 스레드에서 부른다. */
    fun check(ctx: Context, uri: Uri): Result {
        val extractor = MediaExtractor()
        try {
            extractor.setDataSource(ctx, uri, null)
            val track = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
            } ?: return Result.Broken
            extractor.selectTrack(track)
            // 실제 소리 데이터를 한 조각이라도 읽을 수 있어야 진짜 음원으로 본다.
            if (extractor.readSampleData(ByteBuffer.allocate(256 * 1024), 0) <= 0) return Result.Broken
            val format = extractor.getTrackFormat(track)
            val us = if (format.containsKey(MediaFormat.KEY_DURATION)) format.getLong(MediaFormat.KEY_DURATION) else -1L
            val ms = if (us > 0) us / 1000 else durationMs(ctx, uri)
            if (ms in 0..(MIN_SECONDS * 1000L)) return Result.TooShort((ms / 1000).toInt())
            return Result.Ok
        } catch (e: Exception) {
            return Result.Broken
        } finally {
            extractor.release()
        }
    }

    private fun durationMs(ctx: Context, uri: Uri): Long {
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(ctx, uri)
            r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: -1L
        } catch (e: Exception) {
            -1L
        } finally {
            runCatching { r.release() }
        }
    }
}
