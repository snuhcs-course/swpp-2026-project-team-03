// AI-generated with Claude Code, 2026-11-20
package com.team3.rocky.testutil

import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress

/**
 * JVM 단위 테스트용 아주 작은 HTTP 서버 (JDK에 들어 있는 com.sun.net.httpserver).
 * [routes]의 키는 "METHOD /path"(쿼리 포함). 받은 요청은 [requests]에 남는다.
 */
class FakeHttp(private val routes: Map<String, Pair<Int, ByteArray>>) : AutoCloseable {
    data class Request(val method: String, val path: String, val headers: Map<String, String>, val body: ByteArray)

    val requests = mutableListOf<Request>()
    private val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)

    init {
        server.createContext("/") { ex ->
            val path = ex.requestURI.rawPath + (ex.requestURI.rawQuery?.let { "?$it" } ?: "")
            val headers = ex.requestHeaders.mapValues { it.value.firstOrNull().orEmpty() }
                .mapKeys { it.key.lowercase() }
            requests += Request(ex.requestMethod, path, headers, ex.requestBody.readBytes())
            val (code, body) = routes["${ex.requestMethod} $path"] ?: (404 to """{"detail":"not found"}""".toByteArray())
            ex.sendResponseHeaders(code, if (body.isEmpty()) -1 else body.size.toLong())
            if (body.isNotEmpty()) ex.responseBody.use { it.write(body) } else ex.close()
        }
        server.start()
    }

    val url: String get() = "http://127.0.0.1:${server.address.port}"

    override fun close() = server.stop(0)

    companion object {
        fun json(code: Int, text: String) = code to text.toByteArray(Charsets.UTF_8)
    }
}
