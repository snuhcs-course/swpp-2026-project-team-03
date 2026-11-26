// AI-generated with Claude Code, 2026-11-26
package com.team3.rocky.server

import com.team3.rocky.Work
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

/** 보관함 동기화가 서버(/me/works)와 주고받는 모양 */
class LibrarySyncJsonTest {
    @Test fun workGoesToTheServerAndComesBackTheSame() {
        val w = Work(1_764_000_000_000, "Don't Look Back", listOf("piano", "guitar", "guitar2"), "2026.11.26 17:00",
            original = listOf("guitar"), unrecognized = listOf("bass"), personal = true,
            audio = "content://media/1", jobId = "0123456789ab")
        val sent = LibrarySync.toJson(w)
        assertEquals("0123456789ab", sent.getString("job_id"))
        assertFalse(sent.has("audio"))  // 올린 곡 파일 주소는 그 폰에서만 열려서 보내지 않는다
        // 서버는 work_id와 saved_at을 붙여 돌려준다
        val back = LibrarySync.fromJson(JSONObject(sent.toString()).put("work_id", w.id).put("saved_at", 5))
        assertEquals(w.copy(audio = null), back)
    }

    @Test fun missingJobIdStaysNull() {
        val o = JSONObject().put("work_id", 3).put("title", "t").put("job_id", JSONObject.NULL)
        assertNull(LibrarySync.fromJson(o).jobId)
    }
}
