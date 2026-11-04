// AI-generated with Claude Code, 2026-10-15
package com.team3.rocky.auth

import android.content.Context
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isDialog
import androidx.compose.ui.test.performImeAction
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
        val ctx = ApplicationProvider.getApplicationContext<Context>()
        ctx.deleteDatabase(UserDatabase.DB_NAME)
        ctx.getSharedPreferences("rocky_session", Context.MODE_PRIVATE).edit().clear().commit()
    }

    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    private fun waitForText(text: String) =
        rule.waitUntil(10_000) { rule.onAllNodes(hasText(text, substring = true)).fetchSemanticsNodes().isNotEmpty() }

    /** 인증번호 대화상자에 보이는 6자리 숫자 (시연 버전은 메일 대신 화면에 보여준다). */
    private fun shownCode(): String {
        val sixDigits = Regex("^\\d{${EmailVerification.CODE_LENGTH}}$")
        val matcher = SemanticsMatcher("six-digit code") { node ->
            node.config.getOrNull(SemanticsProperties.Text)?.any { sixDigits.matches(it.text) } == true
        }
        rule.waitUntil(5_000) { rule.onAllNodes(matcher).fetchSemanticsNodes().isNotEmpty() }
        return rule.onAllNodes(matcher).fetchSemanticsNodes().first()
            .config[SemanticsProperties.Text].first { sixDigits.matches(it.text) }.text
    }

    @Test fun signUpLogoutLogin() {
        rule.onNodeWithTag("go_signup").performClick()

        // 비어 있는 채로 가입하면 오류가 보이고 가입되지 않는다.
        rule.onNodeWithTag("signup_submit").performClick()
        rule.onNodeWithText("이메일을 입력해 주세요").assertIsDisplayed()

        rule.onNodeWithTag("signup_email").performTextInput("flow@snu.ac.kr")

        // 이메일 인증 (11/3 추가): 번호 받기 → 화면에 보인 번호 입력 → 확인
        rule.onNodeWithText("인증번호 받기").performClick()
        val code = shownCode()
        // 번호 대화상자의 '확인'으로 닫는다 (입력칸 옆에도 '확인'이 있어서 대화상자 안의 것을 고른다)
        rule.onNode(hasText("확인") and hasAnyAncestor(isDialog())).performClick()
        rule.onNodeWithTag("signup_code").performTextInput(code)
        rule.onNodeWithTag("signup_code").performImeAction()   // 키보드 '완료' = 인증번호 확인
        waitForText("인증 완료")
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
