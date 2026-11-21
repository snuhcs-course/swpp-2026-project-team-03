// AI-generated with Claude Code, 2026-11-21
package com.team3.rocky.server

import java.net.HttpURLConnection
import java.net.URL

/**
 * 수업 공개 입구(team3.swpp-2026-b.snu.ac.kr)는 새 연결의 첫 요청을 한 번 돌려보낸다.
 * GET은 302 → /<숫자>/<경로> → 원래 경로로 가고, HttpURLConnection이 따라가면 그 연결은 통과된다.
 * 본문이 있는 요청(POST·PUT·PATCH·DELETE)은 307을 받고 멈춘다 (로그인할 때 "HTTP 307"이 뜨던 원인).
 *
 * 그래서 돌려보내기 응답을 받으면 GET /health를 끝까지 읽어 연결을 통과시킨 뒤 같은 요청을 다시 보낸다.
 * 통과된 연결은 연결 풀에 남아 바로 다음 요청이 쓴다 ('연결 확인' 뒤 다시 하면 되던 것과 같은 원리).
 * 우리 서버(rocky-api)는 돌려보내기 응답을 보내지 않으므로 직접 연결(USB, 에뮬레이터)에는 영향이 없다.
 */
internal object FrontGate {
    /** 한 요청을 보내는 최대 횟수 (처음 1번 + 다시 보내기 2번). */
    const val ATTEMPTS = 3

    fun isBounce(code: Int) = code == 301 || code == 302 || code == 303 || code == 307 || code == 308

    /** 돌려보내기 응답의 본문을 다 읽어서 그 연결을 풀에 돌려준다. */
    fun drain(c: HttpURLConnection) {
        runCatching { (c.errorStream ?: c.inputStream)?.use { it.readBytes() } }
    }

    /**
     * GET /health를 리다이렉트까지 따라가 끝까지 읽는다. 실패해도 무시한다 (다시 보낸 요청이 오류를 알려 준다).
     * disconnect()는 부르지 않는다: 연결을 풀에 남겨야 다음 요청이 통과된 연결을 쓴다.
     */
    fun warm(base: String, apiKey: String) {
        runCatching {
            val c = (URL("$base/health").openConnection() as HttpURLConnection).apply {
                connectTimeout = 5_000
                readTimeout = 5_000
                instanceFollowRedirects = true
                if (apiKey.isNotBlank()) setRequestProperty("X-Rocky-Key", apiKey)
            }
            (if (c.responseCode in 200..299) c.inputStream else c.errorStream)?.use { it.readBytes() }
        }
    }
}
