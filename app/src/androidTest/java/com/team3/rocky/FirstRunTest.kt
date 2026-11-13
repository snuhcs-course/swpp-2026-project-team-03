// AI-generated with Claude Code, 2026-11-13
package com.team3.rocky

import android.content.Context
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** 처음 켤 때: 약관에 동의해야 앱을 쓸 수 있고, 그다음 안내 슬라이드가 나오며 '다시 보지 않기'를 기억한다. */
@RunWith(AndroidJUnit4::class)
class FirstRunTest {
    private val ctx = ApplicationProvider.getApplicationContext<Context>()

    init {
        com.team3.rocky.server.Backend.local = true
        ctx.getSharedPreferences("rocky_first_run", Context.MODE_PRIVATE).edit().clear().commit()
        ctx.getSharedPreferences("rocky_session", Context.MODE_PRIVATE).edit().clear().commit()
        FirstRun.guideShownThisRun = false
    }

    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Test fun termsThenGuide() {
        // 동의 체크 전에는 시작할 수 없다.
        rule.onNodeWithText("동의하고 시작하기").assertIsNotEnabled()
        rule.onNodeWithText("위 내용을 모두 읽었고 동의해요").performClick()
        rule.onNodeWithText("동의하고 시작하기").assertIsEnabled().performClick()
        assertTrue(FirstRun.termsAgreed(ctx))

        // 안내 슬라이드: 다음으로 넘기고, 다시 보지 않기를 골라 닫는다.
        rule.waitUntil(5_000) { rule.onAllNodes(hasText("연습 방식과 악기를 골라요")).fetchSemanticsNodes().isNotEmpty() }
        assertFalse(FirstRun.guideOff(ctx))
        rule.onNodeWithText("다음").performClick()
        rule.waitUntil(5_000) { rule.onAllNodes(hasText("곡을 올려요")).fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText("다시 보지 않기").performClick()
        rule.onNodeWithText("건너뛰기").performClick()
        assertTrue(FirstRun.guideOff(ctx))
        // 로그인 화면으로 들어간다.
        rule.waitUntil(5_000) { rule.onAllNodes(hasText("이메일로 회원가입")).fetchSemanticsNodes().isNotEmpty() }
    }
}
