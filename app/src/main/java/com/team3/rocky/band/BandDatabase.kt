// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.band

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.team3.rocky.Work

/**
 * 기기 안의 밴드 DB (SQLite, 파일 이름 rocky_bands.db). 서버 없이 시험할 때만 쓴다.
 * 앱은 같은 표 구조를 서버로 옮긴 [ServerBandRepository]를 쓴다 (server/rocky_server/accounts.py).
 */
class BandDatabase(context: Context, name: String? = DB_NAME) :
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
                original       TEXT    NOT NULL DEFAULT '',
                shared_by      INTEGER NOT NULL,
                shared_by_name TEXT    NOT NULL,
                shared_at      INTEGER NOT NULL,
                UNIQUE (band_id, work_id)
            )
            """.trimIndent()
        )
        db.execSQL("CREATE INDEX idx_members_user ON band_members(user_id)")
    }

    override fun onOpen(db: SQLiteDatabase) {
        super.onOpen(db)
        // 예전 버전이 넣어 둔 시연용 예시 밴드(초대 코드 BAND33, 가짜 멤버)를 지운다.
        // 예시 밴드의 악보는 앱에 들어 있던 시연용 파일을 썼는데, 그 파일을 11/11에 뺐다.
        if (!db.isReadOnly) db.delete("bands", "invite_code = ? AND owner_id = ?", arrayOf("BAND33", "-1"))
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // 버전 2: 공유 악보에 원곡 구성(original)을 더했다. 기존 밴드·악보는 그대로 둔다.
        if (oldVersion < 2) db.execSQL("ALTER TABLE shared_scores ADD COLUMN original TEXT NOT NULL DEFAULT ''")
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

    fun rename(bandId: Long, name: String) {
        writableDatabase.update("bands", ContentValues().apply { put("name", name) }, "id = ?", arrayOf(bandId.toString()))
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

    /** 닉네임을 바꾸면 내가 들어간 모든 밴드와 내가 공유한 악보에도 반영한다. */
    fun updateNickname(userId: Long, nickname: String) {
        val db = writableDatabase
        db.update("band_members", ContentValues().apply { put("nickname", nickname) }, "user_id = ?", arrayOf(userId.toString()))
        db.update("shared_scores", ContentValues().apply { put("shared_by_name", nickname) }, "shared_by = ?", arrayOf(userId.toString()))
    }

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
            put("original", work.original.joinToString(","))
            put("shared_by", byId); put("shared_by_name", byName); put("shared_at", now)
        }
        return writableDatabase.insertWithOnConflict("shared_scores", null, values, SQLiteDatabase.CONFLICT_IGNORE) != -1L
    }

    fun renameScore(scoreId: Long, title: String) {
        writableDatabase.update("shared_scores", ContentValues().apply { put("title", title) }, "id = ?", arrayOf(scoreId.toString()))
    }

    /** 어느 밴드에든 공유된 악보인지. 공유된 악보는 밴드원이 같은 파일을 열기 때문에 지우지 않는다. */
    fun isWorkShared(workId: Long): Boolean =
        readableDatabase.rawQuery("SELECT 1 FROM shared_scores WHERE work_id = ? LIMIT 1", arrayOf(workId.toString()))
            .use { it.moveToFirst() }

    /** 보관함에서 이름을 바꾸면, 내가 밴드에 공유한 같은 악보의 이름도 바꾼다. */
    fun renameSharedWork(userId: Long, workId: Long, title: String) {
        writableDatabase.update(
            "shared_scores", ContentValues().apply { put("title", title) },
            "shared_by = ? AND work_id = ?", arrayOf(userId.toString(), workId.toString()),
        )
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
                            original = c.str("original").split(",").filter { it.isNotBlank() },
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

    companion object {
        const val DB_NAME = "rocky_bands.db"
        private const val VERSION = 2
    }
}
