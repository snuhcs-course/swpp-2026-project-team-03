// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.band

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.team3.rocky.Demo
import com.team3.rocky.Work

/**
 * 기기 안의 밴드 DB (SQLite, 파일 이름 rocky_bands.db).
 * 지금은 같은 폰 안에서만 밴드를 공유한다. 서버가 생기면 같은 표 구조를 서버로 옮기고
 * [BandRepository]의 서버 구현으로 바꾼다.
 */
class BandDatabase(context: Context, name: String? = DB_NAME, private val seedDemo: Boolean = true) :
    SQLiteOpenHelper(context.applicationContext, name, null, VERSION) {

    override fun onConfigure(db: SQLiteDatabase) {
        db.setForeignKeyConstraintsEnabled(true)
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE bands (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                invite_code TEXT    NOT NULL UNIQUE,
                owner_id    INTEGER NOT NULL,
                created_at  INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE band_members (
                band_id    INTEGER NOT NULL REFERENCES bands(id) ON DELETE CASCADE,
                user_id    INTEGER NOT NULL,
                nickname   TEXT    NOT NULL,
                instrument TEXT    NOT NULL,
                joined_at  INTEGER NOT NULL,
                PRIMARY KEY (band_id, user_id)
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE shared_scores (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                band_id        INTEGER NOT NULL REFERENCES bands(id) ON DELETE CASCADE,
                work_id        INTEGER NOT NULL,
                title          TEXT    NOT NULL,
                instruments    TEXT    NOT NULL,
                work_date      TEXT    NOT NULL,
                shared_by      INTEGER NOT NULL,
                shared_by_name TEXT    NOT NULL,
                shared_at      INTEGER NOT NULL,
                UNIQUE (band_id, work_id)
            )
            """.trimIndent()
        )
        db.execSQL("CREATE INDEX idx_members_user ON band_members(user_id)")
        if (seedDemo) seed(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // 버전 1이 첫 스키마다.
    }

    // ---------- 밴드 ----------

    fun insertBand(name: String, code: String, owner: Long, now: Long): Long =
        writableDatabase.insertOrThrow("bands", null, ContentValues().apply {
            put("name", name); put("invite_code", code); put("owner_id", owner); put("created_at", now)
        })

    fun codeExists(code: String): Boolean =
        readableDatabase.rawQuery("SELECT 1 FROM bands WHERE invite_code = ? LIMIT 1", arrayOf(code))
            .use { it.moveToFirst() }

    fun findBand(id: Long): Band? = oneBand("id = ?", id.toString())

    fun findBandByCode(code: String): Band? = oneBand("invite_code = ?", code)

    fun deleteBand(id: Long) {
        writableDatabase.delete("bands", "id = ?", arrayOf(id.toString()))
    }

    fun setOwner(bandId: Long, userId: Long) {
        writableDatabase.update(
            "bands", ContentValues().apply { put("owner_id", userId) }, "id = ?", arrayOf(bandId.toString()),
        )
    }

    /** 내가 속한 밴드. 최근에 들어간 밴드가 위로 온다. */
    fun bandsOf(userId: Long): List<BandSummary> =
        readableDatabase.rawQuery(
            """
            SELECT b.*, m.instrument AS my_instrument,
                   (SELECT COUNT(*) FROM band_members x WHERE x.band_id = b.id) AS member_count,
                   (SELECT COUNT(*) FROM shared_scores s WHERE s.band_id = b.id) AS score_count
            FROM bands b JOIN band_members m ON m.band_id = b.id
            WHERE m.user_id = ?
            ORDER BY m.joined_at DESC
            """.trimIndent(),
            arrayOf(userId.toString()),
        ).use { c ->
            buildList {
                while (c.moveToNext()) add(
                    BandSummary(
                        band = c.toBand(),
                        memberCount = c.int("member_count"),
                        scoreCount = c.int("score_count"),
                        myInstrument = c.str("my_instrument"),
                    )
                )
            }
        }

    // ---------- 멤버 ----------

    fun insertMember(bandId: Long, userId: Long, nickname: String, instrument: String, now: Long) {
        writableDatabase.insertOrThrow("band_members", null, ContentValues().apply {
            put("band_id", bandId); put("user_id", userId); put("nickname", nickname)
            put("instrument", instrument); put("joined_at", now)
        })
    }

    fun isMember(bandId: Long, userId: Long): Boolean =
        readableDatabase.rawQuery(
            "SELECT 1 FROM band_members WHERE band_id = ? AND user_id = ? LIMIT 1",
            arrayOf(bandId.toString(), userId.toString()),
        ).use { it.moveToFirst() }

    fun deleteMember(bandId: Long, userId: Long) {
        writableDatabase.delete(
            "band_members", "band_id = ? AND user_id = ?", arrayOf(bandId.toString(), userId.toString()),
        )
    }

    /** 먼저 들어온 순서. 방장이 나가면 맨 앞 사람이 방장을 이어받는다. */
    fun members(bandId: Long, ownerId: Long): List<BandMember> =
        readableDatabase.rawQuery(
            "SELECT * FROM band_members WHERE band_id = ? ORDER BY joined_at, user_id",
            arrayOf(bandId.toString()),
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    val uid = c.long("user_id")
                    add(BandMember(uid, c.str("nickname"), c.str("instrument"), isOwner = uid == ownerId))
                }
            }
        }

    // ---------- 공유 악보 ----------

    /** 이미 공유한 악보면 false. */
    fun insertScore(bandId: Long, work: Work, byId: Long, byName: String, now: Long): Boolean {
        val values = ContentValues().apply {
            put("band_id", bandId); put("work_id", work.id); put("title", work.title)
            put("instruments", work.instruments.joinToString(",")); put("work_date", work.date)
            put("shared_by", byId); put("shared_by_name", byName); put("shared_at", now)
        }
        return writableDatabase.insertWithOnConflict("shared_scores", null, values, SQLiteDatabase.CONFLICT_IGNORE) != -1L
    }

    fun scores(bandId: Long): List<SharedScore> =
        readableDatabase.rawQuery(
            "SELECT * FROM shared_scores WHERE band_id = ? ORDER BY shared_at DESC, id DESC",
            arrayOf(bandId.toString()),
        ).use { c ->
            buildList {
                while (c.moveToNext()) add(
                    SharedScore(
                        id = c.long("id"),
                        work = Work(
                            id = c.long("work_id"),
                            title = c.str("title"),
                            instruments = c.str("instruments").split(",").filter { it.isNotBlank() },
                            date = c.str("work_date"),
                        ),
                        sharedById = c.long("shared_by"),
                        sharedByName = c.str("shared_by_name"),
                        sharedAt = c.long("shared_at"),
                    )
                )
            }
        }

    // ---------- 내부 ----------

    private fun oneBand(where: String, arg: String): Band? =
        readableDatabase.query("bands", null, where, arrayOf(arg), null, null, null, "1")
            .use { if (it.moveToFirst()) it.toBand() else null }

    private fun Cursor.toBand() = Band(
        id = long("id"), name = str("name"), inviteCode = str("invite_code"),
        ownerId = long("owner_id"), createdAt = long("created_at"),
    )

    private fun Cursor.str(col: String): String = getString(getColumnIndexOrThrow(col))
    private fun Cursor.long(col: String): Long = getLong(getColumnIndexOrThrow(col))
    private fun Cursor.int(col: String): Int = getInt(getColumnIndexOrThrow(col))

    /**
     * 시연용 예시 밴드. 서버가 없어서 다른 폰의 친구를 데려올 수 없으니,
     * 초대 코드 [DEMO_CODE]로 들어가면 멤버 셋과 공유된 악보 하나가 있는 밴드를 볼 수 있게 한다.
     * 가짜 멤버는 실제 회원 id와 겹치지 않게 음수 id를 쓴다.
     */
    private fun seed(db: SQLiteDatabase) {
        val t = 1_793_350_000_000L   // 2026.10.30 무렵. 순서만 맞으면 된다.
        val bandId = db.insertOrThrow("bands", null, ContentValues().apply {
            put("name", "소개원실 밴드"); put("invite_code", DEMO_CODE); put("owner_id", -1L); put("created_at", t)
        })
        listOf(Triple(-1L, "지민", "guitar"), Triple(-2L, "수빈", "drums"), Triple(-3L, "하늘", "piano"))
            .forEachIndexed { i, (id, nick, inst) ->
                db.insertOrThrow("band_members", null, ContentValues().apply {
                    put("band_id", bandId); put("user_id", id); put("nickname", nick)
                    put("instrument", inst); put("joined_at", t + i)
                })
            }
        db.insertOrThrow("shared_scores", null, ContentValues().apply {
            put("band_id", bandId); put("work_id", 1L); put("title", Demo.SONG_TITLE)
            put("instruments", Demo.INSTRUMENTS.joinToString(",")); put("work_date", "2026.10.30 21:10")
            put("shared_by", -1L); put("shared_by_name", "지민"); put("shared_at", t + 10)
        })
    }

    companion object {
        const val DB_NAME = "rocky_bands.db"
        const val DEMO_CODE = "BAND33"
        private const val VERSION = 1
    }
}
