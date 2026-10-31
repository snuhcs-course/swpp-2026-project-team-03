// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.band

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

class BandRulesTest {
    @Test fun nameIsTrimmedAndLimited() {
        assertNull(BandRules.validateName("  소개원실 밴드  "))
        assertNotNull(BandRules.validateName("   "))
        assertNull(BandRules.validateName("가".repeat(BandRules.NAME_MAX)))
        assertNotNull(BandRules.validateName("가".repeat(BandRules.NAME_MAX + 1)))
    }

    @Test fun codeIsNormalized() {
        assertEquals("BAND33", BandRules.normalizeCode(" band-33 "))
        assertNull(BandRules.validateCode("band 33"))
    }

    @Test fun badCodesAreRejected() {
        assertNotNull(BandRules.validateCode(""))
        assertNotNull(BandRules.validateCode("BAND3"))     // too short
        assertNotNull(BandRules.validateCode("BAND0O"))    // 0 and O are not used
        assertNotNull(BandRules.validateCode("밴드밴드밴드"))
    }

    @Test fun newCodesUseOnlyAllowedCharacters() {
        val random = Random(42)
        repeat(200) {
            val code = BandRules.newCode(random)
            assertEquals(BandRules.CODE_LENGTH, code.length)
            assertTrue(code.all { it in BandRules.CODE_CHARS })
            assertNull(BandRules.validateCode(code))
        }
    }
}
