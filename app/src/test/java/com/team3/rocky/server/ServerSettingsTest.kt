// AI-generated with Claude Code, 2026-11-23
package com.team3.rocky.server

import org.junit.Assert.assertEquals
import org.junit.Test

/** 예전에 저장한 http 공개 주소를 https로 바꿔 쓰는지 (2차 UAT: '연결할 수 없어요'). */
class ServerSettingsTest {
    @Test fun savedHttpPublicAddressBecomesHttps() {
        assertEquals("https://team3.swpp-2026-b.snu.ac.kr", ServerSettings.normalize("http://team3.swpp-2026-b.snu.ac.kr"))
        assertEquals("https://team3.swpp-2026-b.snu.ac.kr", ServerSettings.normalize(" HTTP://team3.swpp-2026-b.snu.ac.kr/ "))
    }

    @Test fun httpsStaysAsIs() {
        assertEquals("https://team3.swpp-2026-b.snu.ac.kr", ServerSettings.normalize("https://team3.swpp-2026-b.snu.ac.kr"))
    }

    @Test fun localDevelopmentAddressesKeepHttp() {
        assertEquals("http://localhost:8000", ServerSettings.normalize("http://localhost:8000"))
        assertEquals("http://127.0.0.1:8080", ServerSettings.normalize("http://127.0.0.1:8080/"))
        assertEquals("http://10.0.2.2:8000", ServerSettings.normalize("http://10.0.2.2:8000"))
    }
}
