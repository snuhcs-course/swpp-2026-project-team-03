package com.team3.rocky.auth

import android.content.Context
import com.team3.rocky.server.MemberApi
import com.team3.rocky.server.MemberApiException
import org.json.JSONArray
import org.json.JSONObject

/** 로그인한 상태. [token]은 서버가 준 값 (폰 안에서만 쓰는 구현은 빈 문자열). */
data class Session(val user: User, val token: String)

/** 회원 정보를 어디에 두는지. 화면 규칙과 세션은 [AuthRepository]가, 저장은 이 인터페이스가 맡는다. */
interface AccountService {
    /** 이메일·닉네임이 이미 있으면 [UserDatabase.DuplicateException]. */
    fun signUp(email: String, password: String, nickname: String, instruments: List<String>, now: Long): Session

    /** 이메일이나 비밀번호가 틀리면 null. */
    fun login(email: String, password: String, now: Long): Session?
    fun emailTaken(email: String): Boolean
    fun nicknameTaken(nickname: String, me: Session?): Boolean

    /** 닉네임이 이미 있으면 [UserDatabase.DuplicateException]. */
    fun updateProfile(me: Session, nickname: String, instruments: List<String>): User
    fun logout(me: Session)
}

/** ROCKY 서버의 회원 DB. 다른 폰에서도 같은 계정으로 로그인하고 같은 밴드에 들어갈 수 있다. */
class ServerAccounts(private val api: (token: String?) -> MemberApi) : AccountService {
    constructor(ctx: Context) : this({ token -> MemberApi.from(ctx.applicationContext, token) })

    override fun signUp(email: String, password: String, nickname: String, instruments: List<String>, now: Long): Session =
        duplicates {
            session(api(null).post("/auth/signup", JSONObject()
                .put("email", email).put("password", password).put("nickname", nickname)
                .put("instruments", JSONArray(instruments))))
        }

    override fun login(email: String, password: String, now: Long): Session? = try {
        session(api(null).post("/auth/login", JSONObject().put("email", email).put("password", password)))
    } catch (e: MemberApiException) {
        if (e.code == 401) null else throw e
    }

    override fun emailTaken(email: String): Boolean =
        JSONObject(api(null).get("/auth/taken?email=" + MemberApi.q(email))).getBoolean("taken")

    override fun nicknameTaken(nickname: String, me: Session?): Boolean =
        JSONObject(api(me?.token).get("/auth/taken?nickname=" + MemberApi.q(nickname))).getBoolean("taken")

    override fun updateProfile(me: Session, nickname: String, instruments: List<String>): User = duplicates {
        user(JSONObject(api(me.token).patch("/me", JSONObject().put("nickname", nickname).put("instruments", JSONArray(instruments)))))
    }

    override fun logout(me: Session) {
        runCatching { api(me.token).post("/auth/logout") }  // 서버에 닿지 않아도 폰에서는 로그아웃한다
    }

    private fun <T> duplicates(block: () -> T): T = try {
        block()
    } catch (e: MemberApiException) {
        if (e.code == 409 && (e.field == "email" || e.field == "nickname")) {
            throw UserDatabase.DuplicateException(if (e.field == "nickname") UserDatabase.C_NICKNAME else "email")
        }
        throw e
    }

    private fun session(text: String): Session {
        val o = JSONObject(text)
        return Session(user(o.getJSONObject("user")), o.getString("token"))
    }

    companion object {
        fun user(o: JSONObject) = User(
            id = o.getLong("id"),
            email = o.getString("email"),
            nickname = o.getString("nickname"),
            instruments = MemberApi.strings(o.optJSONArray("instruments")),
            provider = runCatching { AuthProvider.valueOf(o.optString("provider", "EMAIL")) }.getOrDefault(AuthProvider.EMAIL),
            createdAt = o.optLong("created_at"),
        )

        fun toJson(u: User): JSONObject = JSONObject().put("id", u.id).put("email", u.email).put("nickname", u.nickname)
            .put("instruments", JSONArray(u.instruments)).put("provider", u.provider.name).put("created_at", u.createdAt)
    }
}

/** 폰 안의 회원 DB. 서버 없이 화면을 시험할 때와 테스트에서 쓴다. */
class LocalAccounts(val db: UserDatabase) : AccountService {
    override fun signUp(email: String, password: String, nickname: String, instruments: List<String>, now: Long): Session {
        if (db.emailExists(email)) throw UserDatabase.DuplicateException("email")
        if (db.nicknameExists(nickname)) throw UserDatabase.DuplicateException(UserDatabase.C_NICKNAME)
        val id = db.insert(email, PasswordHasher.hash(password), nickname, instruments, AuthProvider.EMAIL, now)
        db.updateLastLogin(id, now)
        return Session(db.findById(id)!!, "")
    }

    override fun login(email: String, password: String, now: Long): Session? {
        val found = db.findCredentials(email) ?: return null
        if (found.second?.let { PasswordHasher.verify(password, it) } != true) return null
        db.updateLastLogin(found.first.id, now)
        return Session(found.first, "")
    }

    override fun emailTaken(email: String) = db.emailExists(email)

    override fun nicknameTaken(nickname: String, me: Session?) =
        if (me == null) db.nicknameExists(nickname) else db.nicknameTakenByOther(nickname, me.user.id)

    override fun updateProfile(me: Session, nickname: String, instruments: List<String>): User {
        if (db.nicknameTakenByOther(nickname, me.user.id)) throw UserDatabase.DuplicateException(UserDatabase.C_NICKNAME)
        db.updateProfile(me.user.id, nickname, instruments)
        return db.findById(me.user.id)!!
    }

    override fun logout(me: Session) = Unit
}
