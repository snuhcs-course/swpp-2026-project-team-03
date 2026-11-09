package com.team3.rocky.server

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** 서버가 거절한 회원·밴드 요청. [field]는 잘못된 입력칸(email, nickname, code …), 모르면 null. */
class MemberApiException(val code: Int, message: String, val field: String?) : java.io.IOException(message)

/**
 * 회원·밴드 서버 API (server/rocky_server/accounts.py). 로그인하면 받는 토큰을 Authorization 헤더로 보낸다.
 * 네트워크를 쓰므로 Dispatchers.IO에서 부를 것. 서버에 닿지 않으면 IOException.
 */
class MemberApi(baseUrl: String, private val apiKey: String, private val token: String?) {
    private val base = baseUrl.trim().trimEnd('/')

    fun call(method: String, path: String, body: JSONObject? = null): String {
        val c = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 10_000
            readTimeout = 20_000
            if (apiKey.isNotBlank()) setRequestProperty("X-Rocky-Key", apiKey)
            if (!token.isNullOrBlank()) setRequestProperty("Authorization", "Bearer $token")
        }
        try {
            if (body != null) {
                c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                c.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = c.responseCode
            if (code !in 200..299) {
                val text = c.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
                val json = runCatching { JSONObject(text) }.getOrNull()
                val detail = json?.opt("detail") as? String
                val field = json?.optString("field")?.takeIf { it.isNotBlank() && it != "null" }
                throw MemberApiException(code, detail ?: "HTTP $code", field)
            }
            return c.inputStream.bufferedReader().use { it.readText() }
        } finally {
            c.disconnect()
        }
    }

    fun get(path: String) = call("GET", path)
    fun post(path: String, body: JSONObject = JSONObject()) = call("POST", path, body)
    fun patch(path: String, body: JSONObject) = call("PATCH", path, body)

    fun obj(text: String) = JSONObject(text)
    fun arr(text: String) = JSONArray(text)

    companion object {
        fun from(ctx: Context, token: String?) = MemberApi(ServerSettings.url(ctx), ServerSettings.key(ctx), token)

        fun q(s: String): String = URLEncoder.encode(s, "UTF-8")

        fun strings(a: JSONArray?): List<String> =
            if (a == null) emptyList() else (0 until a.length()).map { a.getString(it) }
    }
}
