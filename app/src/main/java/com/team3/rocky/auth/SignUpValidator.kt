// AI-generated with Claude Code, 2026-10-15
package com.team3.rocky.auth

import com.team3.rocky.tr

/** 회원가입 입력 검사. 안드로이드 API를 쓰지 않아 JVM 단위 테스트로 검사할 수 있다. */
object SignUpValidator {
    const val PASSWORD_MIN = 8
    const val PASSWORD_MAX = 64
    const val NICKNAME_MIN = 2
    const val NICKNAME_MAX = 12

    private val EMAIL = Regex("^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\\.[A-Za-z0-9-]+)*\\.[A-Za-z]{2,}$")
    private val NICKNAME = Regex("^[가-힣A-Za-z0-9_]+$")
    // 한글을 치는 도중에는 'ㅎ', 'ㅏ'처럼 낱자가 잠깐 들어온다.
    private val NICKNAME_TYPING = Regex("^[가-힣ㄱ-ㅎㅏ-ㅣA-Za-z0-9_]+$")

    fun normalizeEmail(email: String) = email.trim().lowercase()

    fun emailError(email: String): String? {
        val e = normalizeEmail(email)
        return when {
            e.isEmpty() -> tr("이메일을 입력해 주세요", "Please enter your email")
            e.length > 254 || !EMAIL.matches(e) -> tr("이메일 형식이 올바르지 않아요", "That doesn't look like an email")
            else -> null
        }
    }

    fun passwordError(password: String): String? = when {
        password.isEmpty() -> tr("비밀번호를 입력해 주세요", "Please enter a password")
        password.length < PASSWORD_MIN -> tr("비밀번호는 ${PASSWORD_MIN}자 이상이어야 해요", "Use at least $PASSWORD_MIN characters")
        password.length > PASSWORD_MAX -> tr("비밀번호는 ${PASSWORD_MAX}자 이하여야 해요", "Use at most $PASSWORD_MAX characters")
        password.any { it.isWhitespace() } -> tr("비밀번호에 공백은 쓸 수 없어요", "Passwords can't contain spaces")
        !password.any { it.isLetter() } || !password.any { it.isDigit() } -> tr("영문과 숫자를 모두 포함해 주세요", "Use both letters and numbers")
        else -> null
    }

    fun passwordConfirmError(password: String, confirm: String): String? = when {
        confirm.isEmpty() -> tr("비밀번호를 한 번 더 입력해 주세요", "Please enter the password again")
        confirm != password -> tr("비밀번호가 일치하지 않아요", "Passwords don't match")
        else -> null
    }

    /** @param typing 입력하는 중이면 한글 낱자(ㅎ, ㅏ …)를 오류로 보지 않는다. */
    fun nicknameError(nickname: String, typing: Boolean = false): String? {
        val n = nickname.trim()
        return when {
            n.isEmpty() -> tr("닉네임을 입력해 주세요", "Please enter a nickname")
            n.length < NICKNAME_MIN || n.length > NICKNAME_MAX -> tr("닉네임은 ${NICKNAME_MIN}~${NICKNAME_MAX}자로 정해 주세요", "Use $NICKNAME_MIN–$NICKNAME_MAX characters")
            !(if (typing) NICKNAME_TYPING else NICKNAME).matches(n) -> tr("닉네임은 한글, 영문, 숫자, _만 쓸 수 있어요", "Use only letters, numbers and _")
            else -> null
        }
    }

    fun agreementError(form: SignUpForm): String? = when {
        !form.over14 -> tr("만 14세 이상만 가입할 수 있어요", "You must be 14 or older to sign up")
        !form.agreeTerms || !form.agreePrivacy -> tr("필수 약관에 동의해 주세요", "Please agree to the required terms")
        else -> null
    }

    /** 칸별 오류 메시지. 비어 있으면 가입할 수 있다. */
    fun validate(form: SignUpForm): Map<Field, String> = buildMap {
        emailError(form.email)?.let { put(Field.EMAIL, it) }
        passwordError(form.password)?.let { put(Field.PASSWORD, it) }
        passwordConfirmError(form.password, form.passwordConfirm)?.let { put(Field.PASSWORD_CONFIRM, it) }
        nicknameError(form.nickname)?.let { put(Field.NICKNAME, it) }
        agreementError(form)?.let { put(Field.AGREEMENT, it) }
    }

    enum class Field { EMAIL, PASSWORD, PASSWORD_CONFIRM, NICKNAME, AGREEMENT }
}
