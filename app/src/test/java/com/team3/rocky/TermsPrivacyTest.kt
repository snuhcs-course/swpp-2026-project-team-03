package com.team3.rocky

import com.team3.rocky.auth.privacy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** 베타 계획 3.6절: 약관 6조와 개인정보 동의 화면이 같은 수집 항목과 Google 전송을 알린다. */
class TermsPrivacyTest {
    private val sharedItems = listOf("앱 사용 기록", "기기 모델", "OS 버전", "앱 버전", "오류", "Google(Firebase Crashlytics)", "통계")

    @Test fun termsArticleSixNamesTheNewItemsAndGoogle() {
        val six = termsItems()[5]
        assertTrue(six.title.startsWith("6."))
        sharedItems.forEach { assertTrue("약관 6조에 '$it'이 없음", six.body.contains(it)) }
    }

    @Test fun privacyPolicyListsTheSameItems() {
        val (title, body) = privacy()
        assertEquals("개인정보 수집·이용", title)
        sharedItems.forEach { assertTrue("개인정보 동의에 '$it'이 없음", body.contains(it)) }
        assertTrue(body.contains("기기 식별값"))
        // 회원가입에서 악기를 묻지 않게 된 뒤(11/18)의 문구: 악기는 밴드에서 고르는 선택 항목
        assertTrue(body.contains("밴드에서 연주하는 악기"))
    }

    @Test fun changedTermsAskEveryoneAgain() {
        assertEquals(3, FirstRun.TERMS_VERSION)
    }
}
