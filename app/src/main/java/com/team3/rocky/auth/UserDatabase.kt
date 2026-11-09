// AI-generated with Claude Code, 2026-10-15
package com.team3.rocky.auth

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteConstraintException
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/**
 * 기기 안의 회원 DB (SQLite, 파일 이름 rocky_users.db).
 * 앱은 서버의 회원 DB([ServerAccounts])를 쓰고, 이 클래스는 서버 없이 시험할 때([LocalAccounts])만 쓴다.
 */
class UserDatabase(context: Context, name: String? = DB_NAME) :
    SQLiteOpenHelper(context.applicationContext, name, null, VERSION) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE $T_USERS (
                $C_ID              INTEGER PRIMARY KEY AUTOINCREMENT,
                $C_EMAIL           TEXT    NOT NULL UNIQUE,
                $C_PASSWORD_HASH   TEXT,
                $C_NICKNAME        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                $C_INSTRUMENTS     TEXT    NOT NULL DEFAULT '',
                $C_PROVIDER        TEXT    NOT NULL DEFAULT 'EMAIL',
                $C_PROVIDER_ID     TEXT,
                $C_TERMS_AGREED_AT INTEGER NOT NULL,
                $C_CREATED_AT      INTEGER NOT NULL,
                $C_LAST_LOGIN_AT   INTEGER
            )
            """.trimIndent()
        )
        // 같은 구글·애플 계정으로 두 번 가입되지 않게 한다 (이메일 가입은 provider_id가 NULL).
        db.execSQL("CREATE UNIQUE INDEX idx_users_provider ON $T_USERS($C_PROVIDER, $C_PROVIDER_ID)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // 버전 1이 첫 스키마다. 칸을 바꿀 때는 기존 회원이 지워지지 않도록 ALTER TABLE로 옮긴다.
    }

    /** 새 회원을 저장하고 id를 돌려준다. 이메일이나 닉네임이 이미 있으면 [DuplicateException]. */
    fun insert(
        email: String,
        passwordHash: String?,
        nickname: String,
        instruments: List<String>,
        provider: AuthProvider,
        now: Long,
    ): Long {
        val values = ContentValues().apply {
            put(C_EMAIL, email)
            put(C_PASSWORD_HASH, passwordHash)
            put(C_NICKNAME, nickname)
            put(C_INSTRUMENTS, instruments.joinToString(","))
            put(C_PROVIDER, provider.name)
            put(C_TERMS_AGREED_AT, now)
            put(C_CREATED_AT, now)
        }
        try {
            return writableDatabase.insertOrThrow(T_USERS, null, values)
        } catch (e: SQLiteConstraintException) {
            // 가입 직전에 확인하지만, 동시에 같은 값으로 가입하는 경우를 여기서 막는다.
            throw DuplicateException(if (e.message.orEmpty().contains(C_NICKNAME)) C_NICKNAME else C_EMAIL)
        }
    }

    fun emailExists(email: String) = exists("$C_EMAIL = ?", email)

    fun nicknameExists(nickname: String) = exists("$C_NICKNAME = ? COLLATE NOCASE", nickname)

    fun findById(id: Long): User? = query("$C_ID = ?", id.toString()) { it.toUser() }

    /** 로그인용: 회원과 저장된 비밀번호 해시를 함께 돌려준다. */
    fun findCredentials(email: String): Pair<User, String?>? =
        query("$C_EMAIL = ?", email) { it.toUser() to it.getStringOrNull(C_PASSWORD_HASH) }

    /** 닉네임과 연주하는 악기를 바꾼다. 닉네임이 이미 있으면 [DuplicateException]. */
    fun updateProfile(id: Long, nickname: String, instruments: List<String>) {
        val values = ContentValues().apply {
            put(C_NICKNAME, nickname)
            put(C_INSTRUMENTS, instruments.joinToString(","))
        }
        try {
            writableDatabase.updateWithOnConflict(T_USERS, values, "$C_ID = ?", arrayOf(id.toString()), SQLiteDatabase.CONFLICT_ABORT)
        } catch (e: SQLiteConstraintException) {
            throw DuplicateException(C_NICKNAME)
        }
    }

    /** 다른 회원이 이 닉네임을 쓰고 있는지 (내 닉네임은 빼고 본다). */
    fun nicknameTakenByOther(nickname: String, myId: Long): Boolean =
        readableDatabase.rawQuery(
            "SELECT 1 FROM $T_USERS WHERE $C_NICKNAME = ? COLLATE NOCASE AND $C_ID != ? LIMIT 1",
            arrayOf(nickname, myId.toString()),
        ).use { it.moveToFirst() }

    fun updateLastLogin(id: Long, now: Long) {
        val values = ContentValues().apply { put(C_LAST_LOGIN_AT, now) }
        writableDatabase.update(T_USERS, values, "$C_ID = ?", arrayOf(id.toString()))
    }

    private fun exists(where: String, arg: String): Boolean =
        readableDatabase.rawQuery("SELECT 1 FROM $T_USERS WHERE $where LIMIT 1", arrayOf(arg))
            .use { it.moveToFirst() }

    private fun <R> query(where: String, arg: String, read: (Cursor) -> R): R? =
        readableDatabase.query(T_USERS, null, where, arrayOf(arg), null, null, null, "1")
            .use { if (it.moveToFirst()) read(it) else null }

    private fun Cursor.toUser() = User(
        id = getLong(getColumnIndexOrThrow(C_ID)),
        email = getString(getColumnIndexOrThrow(C_EMAIL)),
        nickname = getString(getColumnIndexOrThrow(C_NICKNAME)),
        instruments = getString(getColumnIndexOrThrow(C_INSTRUMENTS)).split(",").filter { it.isNotBlank() },
        provider = AuthProvider.valueOf(getString(getColumnIndexOrThrow(C_PROVIDER))),
        createdAt = getLong(getColumnIndexOrThrow(C_CREATED_AT)),
    )

    private fun Cursor.getStringOrNull(column: String): String? {
        val i = getColumnIndexOrThrow(column)
        return if (isNull(i)) null else getString(i)
    }

    class DuplicateException(val column: String) : Exception("duplicate $column")

    companion object {
        const val DB_NAME = "rocky_users.db"
        private const val VERSION = 1

        private const val T_USERS = "users"
        private const val C_ID = "id"
        private const val C_EMAIL = "email"
        private const val C_PASSWORD_HASH = "password_hash"
        const val C_NICKNAME = "nickname"
        private const val C_INSTRUMENTS = "instruments"
        private const val C_PROVIDER = "auth_provider"
        private const val C_PROVIDER_ID = "provider_user_id"
        private const val C_TERMS_AGREED_AT = "terms_agreed_at"
        private const val C_CREATED_AT = "created_at"
        private const val C_LAST_LOGIN_AT = "last_login_at"
    }
}
