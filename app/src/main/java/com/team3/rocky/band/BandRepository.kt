// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.band

import android.content.Context
import com.team3.rocky.Work
import com.team3.rocky.auth.User
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 나의 밴드 기능이 쓰는 저장소.
 * 화면은 이 인터페이스만 알기 때문에, 서버가 생기면 [LocalBandRepository] 대신
 * 서버 구현을 끼우면 화면 코드는 그대로 둘 수 있다.
 */
interface BandRepository {
    suspend fun myBands(user: User): List<BandSummary>
    suspend fun detail(bandId: Long): BandDetail?
    suspend fun create(user: User, name: String, instrument: String): BandResult
    suspend fun join(user: User, code: String, instrument: String): BandResult
    suspend fun leave(user: User, bandId: Long)

    /** 새로 공유했으면 true, 이미 공유된 악보면 false. */
    suspend fun share(user: User, bandId: Long, work: Work): Boolean
}

/** 이 폰 안에서만 동작하는 구현 (서버 연결 전 시연용). */
class LocalBandRepository(
    context: Context,
    private val db: BandDatabase = BandDatabase(context),
    private val clock: () -> Long = System::currentTimeMillis,
) : BandRepository {

    override suspend fun myBands(user: User): List<BandSummary> = io { db.bandsOf(user.id) }

    override suspend fun detail(bandId: Long): BandDetail? = io {
        db.findBand(bandId)?.let { BandDetail(it, db.members(it.id, it.ownerId), db.scores(it.id)) }
    }

    override suspend fun create(user: User, name: String, instrument: String): BandResult = io {
        BandRules.validateName(name)?.let { return@io BandResult.Failure(it) }
        val code = generateSequence { BandRules.newCode() }.take(20).firstOrNull { !db.codeExists(it) }
            ?: return@io BandResult.Failure("초대 코드를 만들지 못했어요. 다시 시도해 주세요")
        val now = clock()
        val id = db.writableDatabase.inTransaction {
            val id = db.insertBand(name.trim(), code, user.id, now)
            db.insertMember(id, user.id, user.nickname, instrument, now)
            id
        }
        BandResult.Success(db.findBand(id)!!)
    }

    override suspend fun join(user: User, code: String, instrument: String): BandResult = io {
        BandRules.validateCode(code)?.let { return@io BandResult.Failure(it) }
        val band = db.findBandByCode(BandRules.normalizeCode(code))
            ?: return@io BandResult.Failure("이 초대 코드로 된 밴드가 없어요")
        if (db.isMember(band.id, user.id)) return@io BandResult.Failure("이미 참여 중인 밴드예요")
        db.insertMember(band.id, user.id, user.nickname, instrument, clock())
        BandResult.Success(band)
    }

    override suspend fun leave(user: User, bandId: Long): Unit = io {
        val band = db.findBand(bandId) ?: return@io
        db.writableDatabase.inTransaction {
            db.deleteMember(bandId, user.id)
            val rest = db.members(bandId, band.ownerId)
            when {
                rest.isEmpty() -> db.deleteBand(bandId)               // 마지막 멤버가 나가면 밴드도 지운다
                band.ownerId == user.id -> db.setOwner(bandId, rest.first().userId)
            }
            Unit
        }
    }

    override suspend fun share(user: User, bandId: Long, work: Work): Boolean = io {
        db.insertScore(bandId, work, user.id, user.nickname, clock())
    }

    private suspend fun <T> io(block: () -> T): T = withContext(Dispatchers.IO) { block() }

    private inline fun <T> android.database.sqlite.SQLiteDatabase.inTransaction(block: () -> T): T {
        beginTransaction()
        try {
            val r = block()
            setTransactionSuccessful()
            return r
        } finally {
            endTransaction()
        }
    }
}
