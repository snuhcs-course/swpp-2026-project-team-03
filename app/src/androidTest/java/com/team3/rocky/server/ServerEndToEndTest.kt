package com.team3.rocky.server

import android.content.Context
import android.net.Uri
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.printToString
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.team3.rocky.ExportScreen
import com.team3.rocky.ResultScreen
import com.team3.rocky.RockyTheme
import com.team3.rocky.progress.AudioFile
import com.team3.rocky.progress.ScoreJob
import com.team3.rocky.progress.ScoreJobs
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * 실제 앱 코드로 서버까지 한 바퀴: 업로드 → 진행 상태 → 결과 받기 → 결과·내보내기 화면.
 *
 * 에뮬레이터에서 호스트 PC의 서버(server/, 가짜 파이프라인)를 10.0.2.2:8000으로 부른다.
 * GitHub Actions의 android-e2e 작업이 서버를 먼저 띄운다. 서버가 없으면 이 테스트는 건너뛴다.
 */
@RunWith(AndroidJUnit4::class)
class ServerEndToEndTest {
    @get:Rule val compose = createComposeRule()
    private val ctx: Context = ApplicationProvider.getApplicationContext()
    private val url = InstrumentationRegistry.getArguments().getString("rockyServer") ?: "http://10.0.2.2:8000"

    @Before fun serverIsUp() {
        assumeTrue("ROCKY 서버($url)가 없어서 건너뜀", RockyApi(url, "").health())
        ServerSettings.save(ctx, url, "")
    }

    private fun song(): AudioFile {
        val f = File(ctx.cacheDir, "e2e song.wav")
        f.writeBytes(ByteArray(4096) { (it % 251).toByte() })
        return AudioFile(Uri.fromFile(f), "e2e song.wav")
    }

    private fun waitFor(job: ScoreJob, seconds: Int = 90) {
        repeat(seconds * 4) {
            if (job.done || job.failed) return
            Thread.sleep(250)
        }
    }

    @Test fun songGoesThroughServerAndResultOpens() {
        lateinit var job: ScoreJob
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            job = ScoreJobs.start(ctx, "E2E 곡", listOf("piano", "drums", "bass", "guitar", "guitar2"),
                emptyList(), song())
        }
        waitFor(job)
        assertNull("작업 실패: ${job.error}", job.error)
        assertTrue(job.done)

        // 결과가 폰에 저장됐고, 서버가 판단한 원곡 구성으로 AI 생성 파트(피아노)가 정해진다
        val local = ScoreStore.load(ctx, job.id)
        assertNotNull(local)
        assertEquals(listOf("drums", "bass", "guitar", "guitar2"), job.original)
        assertEquals(setOf("piano"), job.toWork().aiGenerated)
        assertNotNull(local!!.pdf(null))
        assertNotNull(local.midi("guitar"))
        assertNotNull(local.audio(null))            // 밴드 전체 MP3
        assertEquals(local.pdf("guitar"), local.pdf("guitar2"))  // 원곡 기타 2대 → 기타 악보 하나
        assertTrue(PdfPages.render(local.pdf(null)!!, 600).isNotEmpty())

        // 결과 화면: 서버 PDF가 그림으로 보인다
        val work = job.toWork()
        compose.setContent { RockyTheme { ResultScreen(work, onBack = {}, onSaved = {}, onExport = {}, onShareToBand = {}) } }
        // Advance the Compose clock so ResultScreen's LaunchedEffect starts PDF rendering.
        compose.waitForIdle()
        try {
            compose.waitUntil(60_000) { compose.onAllNodesWithContentDescription("악보").fetchSemanticsNodes().isNotEmpty() }
        } catch (e: Throwable) {
            // 무엇이 보이고 있었는지 남긴다 (로딩 중 / '악보가 없어요' / 오류)
            throw AssertionError("결과 화면에 악보가 안 보임. 화면:\n" + compose.onRoot().printToString(maxDepth = 30), e)
        }
        compose.onNodeWithText("✨ 피아노").assertIsDisplayed()
    }

    @Test fun exportListsServerFiles() {
        lateinit var job: ScoreJob
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            job = ScoreJobs.start(ctx, "E2E 내보내기", listOf("drums", "guitar"), listOf("drums", "guitar"), song())
        }
        waitFor(job)
        assertNull("작업 실패: ${job.error}", job.error)
        val work = job.toWork()
        compose.setContent { RockyTheme { ExportScreen(work, onBack = {}) } }
        assertTrue(compose.onAllNodesWithText("MIDI").fetchSemanticsNodes().isNotEmpty())
        assertTrue(compose.onAllNodesWithText("음원").fetchSemanticsNodes().isNotEmpty())
        compose.onNodeWithText("1개 파일 보내기").assertIsDisplayed()
    }

    @Test fun unreachableServerFailsWithMessage() {
        ServerSettings.save(ctx, "http://10.0.2.2:9", "")
        lateinit var job: ScoreJob
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            job = ScoreJobs.start(ctx, "연결 안 됨", listOf("drums"), emptyList(), song())
        }
        waitFor(job, 30)
        assertTrue(job.failed)
        assertTrue(job.error!!.contains("서버에 연결할 수 없어요"))
    }
}
