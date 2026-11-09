// AI-generated with Claude Code, 2026-11-01
package com.team3.rocky.server

import android.content.Context
import com.team3.rocky.BuildConfig
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID

/** 서버가 2xx가 아닌 응답을 보냈을 때. code는 HTTP 상태 코드. */
class ApiException(val code: Int, message: String) : IOException(message)

/** 앱이 쓰는 서버 기능. 테스트에서는 가짜 구현으로 바꾼다. */
interface ScoreServer {
    /**
     * 음원을 올리고 작업 번호를 받는다.
     * @param requested 우리 밴드 구성 (piano·guitar·bass·drums, 기타 2대여도 guitar 하나) → unified.py --requested
     * @param original 사용자가 고른 원곡 구성. 모르면 빈 목록 (서버가 채보 결과로 판단)
     * @param lineup 앱의 밴드 구성 그대로 (guitar2 포함). 서버는 기록만 한다
     */
    fun upload(
        input: InputStream, fileName: String, title: String, requested: List<String>,
        original: List<String> = emptyList(), lineup: List<String> = requested,
    ): String
    fun status(jobId: String): JobStatus
    /** Returns the server state: cancelling, cancelled, or already complete. */
    fun cancel(jobId: String): String
    fun result(jobId: String): JobResult
    fun download(jobId: String, path: String, dest: File)
    /** Re-render a completed score at an absolute offset from its original key. */
    fun transpose(jobId: String, semitones: Int): JobResult =
        throw UnsupportedOperationException("key change is unavailable")
    fun downloadTransposed(jobId: String, semitones: Int, path: String, dest: File): Unit =
        throw UnsupportedOperationException("key change is unavailable")
    /** 서버에 남은 작업과 결과 파일을 지운다. 이미 없으면 그대로 성공으로 본다. */
    fun delete(jobId: String)
}

/**
 * ROCKY 서버(server/) HTTP 클라이언트. 외부 라이브러리 없이 HttpURLConnection만 쓴다.
 * 모든 함수는 네트워크를 쓰므로 Dispatchers.IO에서 부를 것.
 */
class RockyApi(baseUrl: String, private val apiKey: String) : ScoreServer {
    private val base = baseUrl.trim().trimEnd('/')

    private fun open(path: String, method: String = "GET", readTimeoutMs: Int = 30_000): HttpURLConnection =
        (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 10_000
            readTimeout = readTimeoutMs
            if (apiKey.isNotBlank()) setRequestProperty("X-Rocky-Key", apiKey)
        }

    private fun HttpURLConnection.body(): String {
        val code = responseCode
        if (code !in 200..299) {
            val detail = errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
            disconnect()
            throw ApiException(code, "HTTP $code $detail".trim())
        }
        return inputStream.bufferedReader().use { it.readText() }.also { disconnect() }
    }

    fun health(): Boolean = try {
        open("/health").apply { connectTimeout = 3_000; readTimeout = 3_000 }.body().contains("ok")
    } catch (e: Exception) {
        false
    }

    override fun upload(
        input: InputStream, fileName: String, title: String, requested: List<String>,
        original: List<String>, lineup: List<String>,
    ): String {
        val boundary = "rocky-" + UUID.randomUUID()
        val c = open("/jobs", "POST", readTimeoutMs = 120_000)
        c.doOutput = true
        c.setChunkedStreamingMode(64 * 1024)
        c.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        c.outputStream.use { out ->
            fun text(s: String) = out.write(s.toByteArray(Charsets.UTF_8))
            fun field(name: String, value: String) {
                text("--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n$value\r\n")
            }
            field("requested", requested.joinToString(","))
            field("original", original.joinToString(","))
            field("lineup", lineup.joinToString(","))
            field("title", title)
            // 한글 파일 이름도 깨지지 않게 filename*(RFC 5987)도 같이 보낸다.
            val ascii = fileName.filter { it.code in 32..126 && it != '"' }.ifBlank { "song" + extension(fileName) }
            text("--$boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"$ascii\"; " +
                "filename*=UTF-8''${URLEncoder.encode(fileName, "UTF-8").replace("+", "%20")}\r\n" +
                "Content-Type: application/octet-stream\r\n\r\n")
            input.copyTo(out, 64 * 1024)
            text("\r\n--$boundary--\r\n")
        }
        return ApiJson.jobId(c.body())
    }

    override fun status(jobId: String): JobStatus = ApiJson.status(open("/jobs/$jobId").body())

    override fun cancel(jobId: String): String = ApiJson.jobState(open("/jobs/$jobId/cancel", "POST").body())

    override fun result(jobId: String): JobResult = ApiJson.result(open("/jobs/$jobId/result").body())

    override fun transpose(jobId: String, semitones: Int): JobResult =
        ApiJson.result(open("/jobs/$jobId/transpositions/$semitones", "POST", readTimeoutMs = 600_000).body())

    override fun downloadTransposed(jobId: String, semitones: Int, path: String, dest: File) =
        downloadPath("/jobs/$jobId/transpositions/$semitones/files/$path", dest)

    override fun download(jobId: String, path: String, dest: File) {
        downloadPath("/jobs/$jobId/files/$path", dest)
    }

    private fun downloadPath(path: String, dest: File) {
        val c = open(path, readTimeoutMs = 60_000)
        if (c.responseCode !in 200..299) c.body()  // throws ApiException
        dest.parentFile?.mkdirs()
        val tmp = File(dest.path + ".part")
        c.inputStream.use { input -> tmp.outputStream().use { input.copyTo(it) } }
        c.disconnect()
        if (!tmp.renameTo(dest)) throw IOException("could not save $dest")
    }

    override fun delete(jobId: String) {
        val c = open("/jobs/$jobId", "DELETE")
        if (c.responseCode == 404) c.disconnect() else c.body()  // 404 = 이미 지워짐
    }

    companion object {
        fun from(ctx: Context) = RockyApi(ServerSettings.url(ctx), ServerSettings.key(ctx))

        private fun extension(name: String) = name.substringAfterLast('.', "").let { if (it.isEmpty()) "" else ".$it" }
    }
}

/**
 * 서버 주소와 키. 기본값은 빌드할 때 rocky.serverUrl / rocky.apiKey(없으면 http://localhost:8000, 키 없음)이고,
 * 앱의 '서버 설정'에서 바꾸면 그 값이 우선한다.
 * localhost:8000은 폰을 노트북에 연결하고 `adb reverse tcp:8000 tcp:8000`을 했을 때 노트북의 8000번이다.
 */
object ServerSettings {
    private const val PREF = "rocky_server"

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    fun url(ctx: Context): String = prefs(ctx).getString("url", null) ?: BuildConfig.ROCKY_SERVER_URL

    fun key(ctx: Context): String = prefs(ctx).getString("key", null) ?: BuildConfig.ROCKY_API_KEY

    fun isConfigured(ctx: Context) = url(ctx).isNotBlank()

    fun save(ctx: Context, url: String, key: String) {
        prefs(ctx).edit().putString("url", url.trim()).putString("key", key.trim()).apply()
    }
}
