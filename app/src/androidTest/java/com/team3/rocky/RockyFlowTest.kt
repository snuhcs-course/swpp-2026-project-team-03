package com.team3.rocky

import android.app.Activity
import android.app.Instrumentation
import android.content.Context
import android.content.Intent
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.espresso.Espresso
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intended
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.team3.rocky.auth.AuthRepository
import com.team3.rocky.auth.AuthResult
import com.team3.rocky.auth.SignUpForm
import com.team3.rocky.auth.UserDatabase
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * I1–I6: 화면 흐름 테스트 (에뮬레이터 또는 실제 폰 필요)
 * 실행: ./gradlew connectedDebugAndroidTest
 *
 * 앱이 로그인 화면에서 시작하므로, 앱을 띄우기 전에 테스트용 회원으로 가입(=로그인)해 둬요.
 * 그러면 앱이 바로 홈 화면에서 시작해요. (로그인 화면 자체는 auth/AuthFlowTest가 확인)
 */
@RunWith(AndroidJUnit4::class)
class RockyFlowTest {

    init {
        // createAndroidComposeRule이 앱을 띄우기 "전에" 실행돼야 해서 @Before 대신 init을 써요.
        val ctx = ApplicationProvider.getApplicationContext<Context>()
        ctx.deleteDatabase(UserDatabase.DB_NAME)
        ctx.getSharedPreferences("rocky_session", Context.MODE_PRIVATE).edit().clear().commit()
        WorkStore.clear(ctx)
        val result = runBlocking {
            AuthRepository(ctx).signUp(
                SignUpForm(
                    email = "flowtest@snu.ac.kr", password = "band2026", passwordConfirm = "band2026",
                    nickname = "흐름테스트", instruments = emptySet(),   // 기본 선택 악기 없음 (I2용)
                    over14 = true, agreeTerms = true, agreePrivacy = true,
                )
            )
        }
        check(result is AuthResult.Success) { "테스트 회원 가입 실패: $result" }
    }

    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    // ---------- 도우미 ----------
    private fun tag(t: String) = rule.onNodeWithTag(t, useUnmergedTree = true)

    private fun selectInstruments(vararg insts: String) {
        tag("card_new").performClick()
        insts.forEach { tag("tile_$it").performClick() }
    }

    /** 홈 → 악기 선택 → 데모 곡 → 처리 중 → 결과 화면 */
    private fun goToResult(vararg insts: String = arrayOf("piano", "guitar")) {
        selectInstruments(*insts)
        tag("btn_next").performClick()
        tag("btn_demo").performClick()
        tag("btn_start").performClick()
        // 처리 중 애니메이션(약 7초)이 끝날 때까지 기다림
        rule.waitUntil(timeoutMillis = 20_000) {
            rule.onAllNodes(hasTestTag("btn_save"), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun pressBack(times: Int = 1) = repeat(times) {
        Espresso.pressBack()
        rule.waitForIdle()
    }

    // ---------- I1. 전체 흐름 ----------
    @Test
    fun i1_fullFlow_reachesResultScreen() {
        rule.onNodeWithText("흐름테스트님, 반가워요").assertIsDisplayed()   // 로그인된 홈
        tag("card_new").assertIsDisplayed()
        goToResult("piano", "guitar")

        rule.onNodeWithText(Demo.SONG_TITLE).assertIsDisplayed()            // 상단 제목
        tag("part_guitar").assertIsDisplayed()                                // 고른 악기 표시
        tag("part_piano").assertIsDisplayed()
        tag("score").assertIsDisplayed()                                      // 악보 영역
        tag("btn_play").assertIsDisplayed()
        tag("btn_save").assertIsEnabled()
        tag("btn_export").assertIsDisplayed()
    }

    // ---------- I2. 악기 선택 ----------
    @Test
    fun i2_nextButton_dependsOnSelection() {
        tag("card_new").performClick()
        tag("btn_next").assertIsNotEnabled()
        rule.onNodeWithText("다음  (0개 선택)").assertIsDisplayed()

        tag("tile_piano").performClick()
        tag("tile_drums").performClick()
        tag("btn_next").assertIsEnabled()
        rule.onNodeWithText("다음  (2개 선택)").assertIsDisplayed()

        tag("tile_piano").performClick()          // 다시 누르면 선택 해제
        rule.onNodeWithText("다음  (1개 선택)").assertIsDisplayed()
        tag("tile_drums").performClick()
        tag("btn_next").assertIsNotEnabled()
    }

    // ---------- I3. 업로드 ----------
    @Test
    fun i3_startButton_disabledUntilSongChosen() {
        selectInstruments("bass")
        tag("btn_next").performClick()
        tag("btn_start").assertIsNotEnabled()

        tag("btn_demo").performClick()
        tag("btn_start").assertIsEnabled()
        rule.onNodeWithText(Demo.SONG_TITLE).assertIsDisplayed()
    }

    // ---------- I4. 저장 → 보관함 ----------
    @Test
    fun i4_savedWork_appearsInStorage() {
        goToResult("piano")
        tag("btn_save").performClick()
        tag("btn_save").assertIsNotEnabled()
        rule.onNodeWithText("저장됨 ✓").assertIsDisplayed()

        pressBack(3)                               // 결과 → 업로드 → 악기 선택 → 홈
        rule.onNodeWithText("저장한 악보 1개").assertIsDisplayed()

        tag("card_storage").performClick()
        tag("work_item").assertIsDisplayed()
        rule.onNodeWithText(Demo.SONG_TITLE).assertIsDisplayed()

        tag("work_item").performClick()            // 보관함에서 다시 열기
        tag("btn_save").assertIsNotEnabled()       // 이미 저장된 작업
    }

    // ---------- I5. 내보내기 ----------
    @Test
    fun i5_export_shareButtonAndIntent() {
        val files = exportFiles(Assets.list(ctx), Demo.BAND)
        assumeTrue("assets/demo 에 band.pdf 또는 band.mid 가 있어야 합니다", files.isNotEmpty())

        goToResult("piano")
        tag("btn_export").performClick()
        tag("btn_share").assertIsEnabled()                 // 처음엔 모두 체크됨

        files.forEach { (name, _) -> tag("file_$name").performClick() }   // 전부 체크 해제
        tag("btn_share").assertIsNotEnabled()

        tag("file_${files[0].first}").performClick()       // 하나만 다시 체크
        tag("btn_share").assertIsEnabled()

        Intents.init()
        try {
            // 실제 공유 창은 띄우지 않고, 공유 요청(Intent)이 나갔는지만 확인
            intending(hasAction(Intent.ACTION_CHOOSER))
                .respondWith(Instrumentation.ActivityResult(Activity.RESULT_OK, null))
            tag("btn_share").performClick()
            intended(hasAction(Intent.ACTION_CHOOSER))
        } finally {
            Intents.release()
        }
    }

    // ---------- I6. 뒤로가기 ----------
    @Test
    fun i6_backNavigation() {
        selectInstruments("piano")
        tag("btn_next").performClick()
        tag("btn_start").assertIsDisplayed()               // 업로드 화면

        pressBack()
        tag("btn_next").assertIsDisplayed()                // 악기 선택 화면
        pressBack()
        tag("card_new").assertIsDisplayed()                // 홈

        tag("card_storage").performClick()
        tag("btn_back").performClick()                     // 화면 위 ← 버튼
        tag("card_new").assertIsDisplayed()

        val activity = rule.activity
        Espresso.pressBackUnconditionally()                // 홈에서 뒤로가기 → 앱 종료
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        assertTrue(activity.isFinishing || activity.isDestroyed)
    }
}
