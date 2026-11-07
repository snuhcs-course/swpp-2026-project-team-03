// AI-generated with Claude Code, 2026-10-15
package com.team3.rocky.auth

import com.team3.rocky.tr

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

sealed class AuthResult {
    data class Success(val user: User) : AuthResult()
    /** 칸별 오류. 화면은 해당 입력칸 아래에 메시지를 보여준다. */
    data class Invalid(val errors: Map<SignUpValidator.Field, String>) : AuthResult()
    data class Failure(val message: String) : AuthResult()
}

/**
 * 회원가입·로그인·로그아웃과 로그인 상태(세션)를 맡는다.
 * 세션은 로그인한 회원 id 하나를 SharedPreferences에 저장하는 방식이라 앱을 껐다 켜도 유지된다.
 */
class AuthRepository(
    context: Context,
    private val db: UserDatabase = UserDatabase(context),
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val prefs = context.applicationContext.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    suspend fun signUp(form: SignUpForm): AuthResult = withContext(Dispatchers.IO) {
        val errors = SignUpValidator.validate(form).toMutableMap()
        val email = SignUpValidator.normalizeEmail(form.email)
        val nickname = form.nickname.trim()
        if (SignUpValidator.Field.EMAIL !in errors && db.emailExists(email)) {
            errors[SignUpValidator.Field.EMAIL] = tr("이미 가입된 이메일이에요", "This email is already registered")
        }
        if (SignUpValidator.Field.NICKNAME !in errors && db.nicknameExists(nickname)) {
            errors[SignUpValidator.Field.NICKNAME] = tr("이미 사용 중인 닉네임이에요", "This nickname is taken")
        }
        if (errors.isNotEmpty()) return@withContext AuthResult.Invalid(errors)

        val now = clock()
        val id = try {
            db.insert(
                email = email,
                passwordHash = PasswordHasher.hash(form.password),
                nickname = nickname,
                instruments = INSTRUMENT_ORDER.filter { it in form.instruments },
                provider = AuthProvider.EMAIL,
                now = now,
            )
        } catch (e: UserDatabase.DuplicateException) {
            val field = if (e.column == UserDatabase.C_NICKNAME) SignUpValidator.Field.NICKNAME else SignUpValidator.Field.EMAIL
            val message = if (field == SignUpValidator.Field.NICKNAME) tr("이미 사용 중인 닉네임이에요", "This nickname is taken") else tr("이미 가입된 이메일이에요", "This email is already registered")
            return@withContext AuthResult.Invalid(mapOf(field to message))
        }
        // 가입하면 바로 로그인된 상태로 시작한다.
        db.updateLastLogin(id, now)
        startSession(id)
        AuthResult.Success(db.findById(id)!!)
    }

    suspend fun login(email: String, password: String): AuthResult = withContext(Dispatchers.IO) {
        val normalized = SignUpValidator.normalizeEmail(email)
        if (normalized.isEmpty() || password.isEmpty()) {
            return@withContext AuthResult.Failure(tr("이메일과 비밀번호를 입력해 주세요", "Please enter your email and password"))
        }
        val found = db.findCredentials(normalized)
        // 없는 이메일인지 틀린 비밀번호인지 알려주지 않는다 (가입 여부를 알아내는 것을 막기 위해).
        val ok = found != null && found.second?.let { PasswordHasher.verify(password, it) } == true
        if (!ok) return@withContext AuthResult.Failure(WRONG_CREDENTIALS)
        val user = found!!.first
        db.updateLastLogin(user.id, clock())
        startSession(user.id)
        AuthResult.Success(user)
    }

    /** 회원가입 화면에서 입력하는 동안 바로 알려주기 위한 중복 확인. */
    suspend fun isEmailTaken(email: String): Boolean = withContext(Dispatchers.IO) {
        db.emailExists(SignUpValidator.normalizeEmail(email))
    }

    suspend fun isNicknameTaken(nickname: String, exceptUserId: Long? = null): Boolean = withContext(Dispatchers.IO) {
        val n = nickname.trim()
        if (exceptUserId == null) db.nicknameExists(n) else db.nicknameTakenByOther(n, exceptUserId)
    }

    /** 내 정보 수정. 성공하면 바뀐 회원 정보를, 실패하면 화면에 보여줄 메시지를 돌려준다. */
    suspend fun updateProfile(user: User, nickname: String, instruments: Set<String>): Result<User> =
        withContext(Dispatchers.IO) {
            val n = nickname.trim()
            SignUpValidator.nicknameError(n)?.let { return@withContext Result.failure(IllegalArgumentException(it)) }
            if (db.nicknameTakenByOther(n, user.id)) {
                return@withContext Result.failure(IllegalArgumentException(tr("이미 사용 중인 닉네임이에요", "This nickname is taken")))
            }
            try {
                db.updateProfile(user.id, n, INSTRUMENT_ORDER.filter { it in instruments })
            } catch (e: UserDatabase.DuplicateException) {
                return@withContext Result.failure(IllegalArgumentException(tr("이미 사용 중인 닉네임이에요", "This nickname is taken")))
            }
            Result.success(db.findById(user.id)!!)
        }

    fun logout() {
        prefs.edit().remove(KEY_USER_ID).apply()
    }

    /** 로그인한 회원. 로그인하지 않았거나 회원 정보가 없으면 null. */
    fun currentUser(): User? {
        val id = prefs.getLong(KEY_USER_ID, NO_USER)
        if (id == NO_USER) return null
        return db.findById(id) ?: run { logout(); null }
    }

    private fun startSession(id: Long) {
        prefs.edit().putLong(KEY_USER_ID, id).apply()
    }

    companion object {
        val WRONG_CREDENTIALS get() = tr("이메일 또는 비밀번호가 맞지 않아요", "Wrong email or password")
        private const val PREF = "rocky_session"
        private const val KEY_USER_ID = "user_id"
        private const val NO_USER = -1L
        private val INSTRUMENT_ORDER = listOf("piano", "drums", "bass", "guitar", "vocal")

        /** 보관함처럼 회원별로 나눠 저장하는 데이터가 쓰는 현재 회원 id. 로그인 전이면 null. */
        fun currentUserId(context: Context): Long? =
            context.getSharedPreferences(PREF, Context.MODE_PRIVATE).getLong(KEY_USER_ID, NO_USER)
                .takeIf { it != NO_USER }
    }
}
