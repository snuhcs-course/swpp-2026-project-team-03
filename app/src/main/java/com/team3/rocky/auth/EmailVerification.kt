package com.team3.rocky.auth

import com.team3.rocky.tr

import kotlin.random.Random

/**
 * 이메일 인증번호 (시연용).
 * 서버가 없어서 메일을 보내지 못하므로, 만든 번호를 화면에 보여주고 사용자가 그대로 입력하게 한다.
 * 서버가 생기면 [send]는 서버에 메일 발송을 요청하고, [check]는 서버에 확인을 맡긴다.
 */
class EmailVerification(private val random: Random = Random.Default, private val clock: () -> Long = System::currentTimeMillis) {
    private var email: String? = null
    private var code: String? = null
    private var sentAt = 0L

    /** 새 인증번호를 만든다. 시연 버전은 이 번호를 화면에 보여준다. */
    fun send(email: String): String {
        val c = (1..CODE_LENGTH).map { random.nextInt(10) }.joinToString("")
        this.email = SignUpValidator.normalizeEmail(email)
        code = c
        sentAt = clock()
        return c
    }

    /** 맞으면 null, 틀리면 화면에 보여줄 메시지. */
    fun check(email: String, input: String): String? = when {
        code == null || this.email != SignUpValidator.normalizeEmail(email) -> tr("인증번호를 먼저 받아 주세요", "Please get a code first")
        clock() - sentAt > VALID_MS -> tr("인증번호 유효 시간이 지났어요. 다시 받아 주세요", "The code expired. Please get a new one")
        input.trim() != code -> tr("인증번호가 맞지 않아요", "That code isn't right")
        else -> null
    }

    companion object {
        const val CODE_LENGTH = 6
        const val VALID_MS = 5 * 60 * 1000L
    }
}
