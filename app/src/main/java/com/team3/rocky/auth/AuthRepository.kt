// AI-generated with Claude Code, 2026-10-15
package com.team3.rocky.auth

import android.content.Context
import com.team3.rocky.server.Backend
import com.team3.rocky.tr
import com.team3.rocky.server.MemberApiException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException

sealed class AuthResult {
    data class Success(val user: User) : AuthResult()
    /** 칸별 오류. 화면은 해당 입력칸 아래에 메시지를 보여준다. */
    data class Invalid(val errors: Map<SignUpValidator.Field, String>) : AuthResult()
    data class Failure(val message: String) : AuthResult()
}

/**
 * 회원가입·로그인·로그아웃과 로그인 상태(세션)를 맡는다.
 * 회원 정보는 [accounts]에 둔다 (앱은 ROCKY 서버, 테스트는 폰 안의 DB).
 * 세션은 회원 정보와 서버 토큰을 SharedPreferences에 저장해서 앱을 껐다 켜도, 서버에 닿지 않아도 유지된다.
 */
class AuthRepository(
    context: Context,
    private val accounts: AccountService = Backend.accounts(context),
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val prefs = context.applicationContext.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    suspend fun signUp(form: SignUpForm): AuthResult = withContext(Dispatchers.IO) {
        val errors = SignUpValidator.validate(form).toMutableMap()
        if (errors.isNotEmpty()) return@withContext AuthResult.Invalid(errors)
        val email = SignUpValidator.normalizeEmail(form.email)
        val nickname = form.nickname.trim()
        try {
            val s = accounts.signUp(email, form.password, nickname, INSTRUMENT_ORDER.filter { it in form.instruments }, clock())
            // 가입하면 바로 로그인된 상태로 시작한다.
            startSession(s)
            AuthResult.Success(s.user)
        } catch (e: UserDatabase.DuplicateException) {
            val field = if (e.column == UserDatabase.C_NICKNAME) SignUpValidator.Field.NICKNAME else SignUpValidator.Field.EMAIL
            val message = if (field == SignUpValidator.Field.NICKNAME) tr("이미 사용 중인 닉네임이에요", "This nickname is taken")
                else tr("이미 가입된 이메일이에요", "This email is already registered")
            AuthResult.Invalid(mapOf(field to message))
        } catch (e: MemberApiException) {
            AuthResult.Failure(e.message ?: OFFLINE)
        } catch (e: IOException) {
            AuthResult.Failure(OFFLINE)
        }
    }

    suspend fun login(email: String, password: String): AuthResult = withContext(Dispatchers.IO) {
        val normalized = SignUpValidator.normalizeEmail(email)
        if (normalized.isEmpty() || password.isEmpty()) {
            return@withContext AuthResult.Failure(tr("이메일과 비밀번호를 입력해 주세요", "Enter your email and password"))
        }
        // 없는 이메일인지 틀린 비밀번호인지 알려주지 않는다 (가입 여부를 알아내는 것을 막기 위해).
        val s = try {
            accounts.login(normalized, password, clock())
        } catch (e: MemberApiException) {
            return@withContext AuthResult.Failure(e.message ?: OFFLINE)
        } catch (e: IOException) {
            return@withContext AuthResult.Failure(OFFLINE)
        } ?: return@withContext AuthResult.Failure(WRONG_CREDENTIALS)
        startSession(s)
        AuthResult.Success(s.user)
    }

    /** 회원가입 화면에서 입력하는 동안 바로 알려주기 위한 중복 확인. 서버에 닿지 않으면 false (가입할 때 다시 확인한다). */
    suspend fun isEmailTaken(email: String): Boolean = withContext(Dispatchers.IO) {
        runCatching { accounts.emailTaken(SignUpValidator.normalizeEmail(email)) }.getOrDefault(false)
    }

    suspend fun isNicknameTaken(nickname: String, exceptUserId: Long? = null): Boolean = withContext(Dispatchers.IO) {
        val me = session()?.takeIf { exceptUserId != null && it.user.id == exceptUserId }
        runCatching { accounts.nicknameTaken(nickname.trim(), me) }.getOrDefault(false)
    }

    /** 내 정보 수정. 성공하면 바뀐 회원 정보를, 실패하면 화면에 보여줄 메시지를 돌려준다. */
    suspend fun updateProfile(user: User, nickname: String, instruments: Set<String>): Result<User> =
        withContext(Dispatchers.IO) {
            val n = nickname.trim()
            SignUpValidator.nicknameError(n)?.let { return@withContext Result.failure(IllegalArgumentException(it)) }
            val me = session()?.takeIf { it.user.id == user.id } ?: Session(user, "")
            try {
                val updated = accounts.updateProfile(me, n, INSTRUMENT_ORDER.filter { it in instruments })
                startSession(Session(updated, me.token))
                Result.success(updated)
            } catch (e: UserDatabase.DuplicateException) {
                Result.failure(IllegalArgumentException(tr("이미 사용 중인 닉네임이에요", "This nickname is taken")))
            } catch (e: MemberApiException) {
                Result.failure(IllegalArgumentException(e.message ?: OFFLINE))
            } catch (e: IOException) {
                Result.failure(IllegalArgumentException(OFFLINE))
            }
        }

    fun logout() {
        val s = session()
        prefs.edit().remove(KEY_USER_ID).remove(KEY_TOKEN).remove(KEY_USER).apply()
        if (s != null && s.token.isNotEmpty()) Thread { accounts.logout(s) }.start()
    }

    /** 로그인한 회원. 로그인하지 않았으면 null. */
    fun currentUser(): User? = session()?.user

    private fun session(): Session? {
        if (prefs.getLong(KEY_USER_ID, NO_USER) == NO_USER) return null
        val user = prefs.getString(KEY_USER, null)?.let { runCatching { ServerAccounts.user(JSONObject(it)) }.getOrNull() }
            ?: return null
        val token = prefs.getString(KEY_TOKEN, "").orEmpty()
        // 서버를 쓰는데 토큰이 없으면 예전(폰 안에만 저장하던) 로그인이다. 다시 로그인하게 한다.
        if (token.isEmpty() && accounts !is LocalAccounts) return null
        return Session(user, token)
    }

    private fun startSession(s: Session) {
        prefs.edit().putLong(KEY_USER_ID, s.user.id).putString(KEY_TOKEN, s.token)
            .putString(KEY_USER, ServerAccounts.toJson(s.user).toString()).apply()
    }

    companion object {
        val WRONG_CREDENTIALS get() = tr("이메일 또는 비밀번호가 맞지 않아요", "Wrong email or password")
        val OFFLINE get() = tr(
            "서버에 연결하지 못했어요. 인터넷이나 연결 설정을 확인해 주세요",
            "Can't reach the server. Check the internet or connection settings",
        )
        private const val PREF = "rocky_session"
        private const val KEY_USER_ID = "user_id"
        private const val KEY_TOKEN = "token"
        private const val KEY_USER = "user"
        private const val NO_USER = -1L
        private val INSTRUMENT_ORDER = listOf("piano", "drums", "bass", "guitar", "vocal")

        /** 보관함처럼 회원별로 나눠 저장하는 데이터가 쓰는 현재 회원 id. 로그인 전이면 null. */
        fun currentUserId(context: Context): Long? =
            context.getSharedPreferences(PREF, Context.MODE_PRIVATE).getLong(KEY_USER_ID, NO_USER)
                .takeIf { it != NO_USER }

        /** 서버 API에 보낼 로그인 토큰. 로그인 전이면 null. */
        fun token(context: Context): String? =
            context.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY_TOKEN, null)?.takeIf { it.isNotEmpty() }
    }
}
