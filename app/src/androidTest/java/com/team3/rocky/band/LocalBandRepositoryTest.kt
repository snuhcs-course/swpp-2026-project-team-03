// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.band

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.team3.rocky.Work
import com.team3.rocky.auth.AuthProvider
import com.team3.rocky.auth.User
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LocalBandRepositoryTest {
    private val ctx = ApplicationProvider.getApplicationContext<Context>()
    private lateinit var db: BandDatabase
    private lateinit var repo: LocalBandRepository
    private var now = 1_000L

    private val me = user(1, "락스타", "bass")
    private val friend = user(2, "드러머", "drums")
    private val work = Work(id = 77, title = "Immigrant Song", instruments = listOf("drums", "bass", "guitar"), date = "2026.10.31 12:00")

    private fun user(id: Long, nick: String, inst: String) =
        User(id, "u$id@snu.ac.kr", nick, listOf(inst), AuthProvider.EMAIL, 0)

    @Before fun setUp() {
        db = BandDatabase(ctx, name = null)   // in-memory, with the demo band
        repo = LocalBandRepository(ctx, db) { now++ }
    }

    @After fun tearDown() { db.close() }

    @Test fun createMakesMeOwnerAndMember() = runBlocking {
        val band = (repo.create(me, "  우리 밴드 ", "bass") as BandResult.Success).band
        assertEquals("우리 밴드", band.name)
        assertEquals(me.id, band.ownerId)
        assertNull(BandRules.validateCode(band.inviteCode))

        val mine = repo.myBands(me).single()
        assertEquals(band.id, mine.band.id)
        assertEquals("bass", mine.myInstrument)
        assertEquals(1, mine.memberCount)
    }

    @Test fun createRejectsBlankName() = runBlocking {
        assertTrue(repo.create(me, "  ", "bass") is BandResult.Failure)
        assertTrue(repo.myBands(me).isEmpty())
    }

    @Test fun friendJoinsWithCodeOnce() = runBlocking {
        val band = (repo.create(me, "우리 밴드", "bass") as BandResult.Success).band
        val joined = repo.join(friend, band.inviteCode.lowercase(), "drums") as BandResult.Success
        assertEquals(band.id, joined.band.id)
        assertTrue(repo.join(friend, band.inviteCode, "drums") is BandResult.Failure)
        assertTrue(repo.join(friend, "ZZZZZZ", "drums") is BandResult.Failure)

        val detail = repo.detail(band.id)!!
        assertEquals(listOf("락스타", "드러머"), detail.members.map { it.nickname })
        assertEquals("drums", detail.instrumentOf(friend.id))
        assertTrue(detail.members.first { it.userId == me.id }.isOwner)
    }

    @Test fun demoBandCanBeJoined() = runBlocking {
        val band = (repo.join(me, BandDatabase.DEMO_CODE, "bass") as BandResult.Success).band
        val detail = repo.detail(band.id)!!
        assertEquals(4, detail.members.size)
        assertEquals(1, detail.scores.size)
    }

    @Test fun sharingTheSameScoreTwiceKeepsOne() = runBlocking {
        val band = (repo.create(me, "우리 밴드", "bass") as BandResult.Success).band
        assertTrue(repo.share(me, band.id, work))
        assertFalse(repo.share(me, band.id, work))

        val score = repo.detail(band.id)!!.scores.single()
        assertEquals(work, score.work)
        assertEquals("락스타", score.sharedByName)
    }

    @Test fun ownerLeavingHandsOverAndLastLeaveDeletes() = runBlocking {
        val band = (repo.create(me, "우리 밴드", "bass") as BandResult.Success).band
        repo.join(friend, band.inviteCode, "drums")
        repo.share(me, band.id, work)

        repo.leave(me, band.id)
        val after = repo.detail(band.id)!!
        assertEquals(friend.id, after.band.ownerId)
        assertEquals(1, after.scores.size)        // my shared score stays
        assertTrue(repo.myBands(me).isEmpty())

        repo.leave(friend, band.id)
        assertNull(repo.detail(band.id))
    }
}
