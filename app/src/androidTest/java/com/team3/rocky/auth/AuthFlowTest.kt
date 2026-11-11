// AI-generated with Claude Code, 2026-10-15
package com.team3.rocky.auth

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.team3.rocky.MainActivity
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** 실제 앱 화면으로 회원가입 → 로그아웃 → 로그인을 거친다. 시작 전에 앱의 회원 DB와 세션을 지운다. */
@RunWith(AndroidJUnit4::class)
class AuthFlowTest {
    init {
        com.team3.rocky.server.Backend.local = true  // 서버 없이 폰 안의 회원 DB로 화면을 시험한다
        val ctx = ApplicationProvider.getApplicationContext<Context>()
        ctx.deleteDatabase(UserDatabase.DB_NAME)
        ctx.getSharedPreferences("rocky_session", Context.MODE_PRIVATE).edit().clear().commit()
    }

    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    private fun waitForText(text: String) =
        rule.waitUntil(10_000) { rule.onAllNodes(hasText(text, substring = true)).fetchSemanticsNodes().isNotEmpty() }

    @Test fun signUpLogoutLogin() {
        rule.onNodeWithTag("go_signup").performClick()

        // 비어 있는 채로 가입하면 오류가 보이고 가입되지 않는다.
        rule.onNodeWithTag("signup_submit").performClick()
        rule.onNodeWithText("이메일을 입력해 주세요").assertIsDisplayed()

        rule.onNodeWithTag("signup_email").performTextInput("flow@snu.ac.kr")

        // 이메일 인증번호 절차는 11/11에 뺐다: 이메일만 입력하면 된다.
        rule.onNodeWithTag("signup_password").performTextInput("band2026")
        rule.onNodeWithTag("signup_password_confirm").performTextInput("band2026")
        rule.onNodeWithTag("signup_nickname").performTextInput("테스트밴드")
        rule.onNodeWithTag("instrument_guitar").performScrollTo().performClick()
        rule.onNodeWithTag("agree_all").performScrollTo().performClick()
        rule.onNodeWithTag("signup_submit").performClick()

        waitForText("테스트밴드님, 반가워요")
        rule.onNodeWithText("내 정보").performClick()
        rule.onNodeWithText("flow@snu.ac.kr").assertIsDisplayed()
        rule.onNodeWithText("기타").assertIsDisplayed()
        rule.onNodeWithTag("logout").performScrollTo().performClick()
        rule.onNodeWithTag("logout_confirm").performClick()

        rule.onNodeWithTag("login_email").performTextInput("flow@snu.ac.kr")
        rule.onNodeWithTag("login_password").performTextInput("wrong2026")
        rule.onNodeWithTag("login_submit").performClick()
        waitForText(AuthRepository.WRONG_CREDENTIALS)

        rule.onNodeWithTag("login_password").performTextClearance()
        rule.onNodeWithTag("login_password").performTextInput("band2026")
        rule.onNodeWithTag("login_submit").performClick()
        waitForText("테스트밴드님, 반가워요")

        // 앱을 다시 띄워도 로그인 상태가 유지된다.
        rule.activityRule.scenario.recreate()
        waitForText("테스트밴드님, 반가워요")
    }
}
