package com.team3.rocky.server

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.team3.rocky.band.BandDatabase
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.IOException
import java.io.InputStream

/** 보관함에서 지운 악보가 폰과 서버에서 지워지는지 (NFR-07). */
@RunWith(AndroidJUnit4::class)
class ServerCleanupTest {
    private val ctx = ApplicationProvider.getApplicationContext<Context>()
    private val workId = 424242L

    /** 지운 작업 번호를 기록하는 가짜 서버. offline이면 연결 실패를 흉내 낸다. */
    private class FakeServer : ScoreServer {
        val deleted = mutableListOf<String>()
        var offline = false
        override fun delete(jobId: String) {
            if (offline) throw IOException("no route")
            deleted += jobId
        }
        override fun upload(
            input: InputStream, fileName: String, title: String, requested: List<String>,
            original: List<String>, lineup: List<String>,
        ) = throw UnsupportedOperationException()
        override fun status(jobId: String) = throw UnsupportedOperationException()
        override fun cancel(jobId: String) = throw UnsupportedOperationException()
        override fun result(jobId: String) = throw UnsupportedOperationException()
        override fun download(jobId: String, path: String, dest: File) = throw UnsupportedOperationException()
    }

    private val server = FakeServer()
    private var shared = false
    private val oldFactory = ServerCleanup.serverFactory
    private val oldShared = ServerCleanup.isShared

    @Before fun setUp() {
        ServerCleanup.serverFactory = { server }
        ServerCleanup.isShared = { _, _ -> shared }
        ServerCleanup.retryNow(ctx)  // 다른 테스트가 남긴 작업 비우기
        server.deleted.clear()
        // 서버에서 받아 둔 결과처럼 result.json을 만든다.
        ScoreStore.dir(ctx, workId).apply { mkdirs() }.resolve("result.json").writeText(
            """{"id":"abc123abc123","title":"t","full_band":{"pdf":"scores/full_band.pdf"},"instruments":{}}""",
        )
    }

    @After fun tearDown() {
        ServerCleanup.serverFactory = oldFactory
        ServerCleanup.isShared = oldShared
        ScoreStore.dir(ctx, workId).deleteRecursively()
    }

    @Test fun deletesPhoneFilesAndServerJob() {
        assertTrue(ServerCleanup.deleteNow(ctx, workId))
        assertEquals(listOf("abc123abc123"), server.deleted)
        assertFalse(ScoreStore.dir(ctx, workId).exists())
        assertTrue(ServerCleanup.pending(ctx).isEmpty())
    }

    @Test fun sharedScoreIsKept() {
        shared = true
        assertFalse(ServerCleanup.deleteNow(ctx, workId))
        assertTrue(server.deleted.isEmpty())
        assertTrue(ScoreStore.dir(ctx, workId).exists())
    }

    @Test fun offlineDeleteIsRetriedLater() {
        server.offline = true
        assertFalse(ServerCleanup.deleteNow(ctx, workId))
        assertEquals(setOf("abc123abc123"), ServerCleanup.pending(ctx))
        server.offline = false
        assertEquals(setOf("abc123abc123"), ServerCleanup.retryNow(ctx))
        assertTrue(ServerCleanup.pending(ctx).isEmpty())
    }

    @Test fun bandDatabaseKnowsSharedWorks() {
        val db = BandDatabase(ctx, name = null)
        try {
            assertTrue(db.isWorkShared(1L))  // the demo band's shared song
            assertFalse(db.isWorkShared(workId))
        } finally {
            db.close()
        }
    }
}
