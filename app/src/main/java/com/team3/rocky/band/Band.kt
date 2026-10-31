// AI-generated with Claude Code, 2026-10-31
package com.team3.rocky.band

import com.team3.rocky.Work
import kotlin.random.Random

/** 밴드. 초대 코드를 아는 사람은 누구나 참여할 수 있다. */
data class Band(
    val id: Long,
    val name: String,
    val inviteCode: String,
    val ownerId: Long,
    val createdAt: Long,
)

/** 밴드 멤버. 한 밴드 안에서 한 사람은 악기 하나를 맡는다. */
data class BandMember(
    val userId: Long,
    val nickname: String,
    /** piano, drums, bass, guitar 중 하나 */
    val instrument: String,
    val isOwner: Boolean,
)

/** 밴드에 공유된 악보. 공유한 시점의 악보 정보를 복사해 둔다. */
data class SharedScore(
    val id: Long,
    val work: Work,
    val sharedById: Long,
    val sharedByName: String,
    val sharedAt: Long,
)

/** 밴드 목록 화면에 보여줄 요약. */
data class BandSummary(
    val band: Band,
    val memberCount: Int,
    val scoreCount: Int,
    /** 이 밴드에서 내가 맡은 악기 */
    val myInstrument: String,
)

data class BandDetail(
    val band: Band,
    val members: List<BandMember>,
    val scores: List<SharedScore>,
) {
    fun instrumentOf(userId: Long): String? = members.firstOrNull { it.userId == userId }?.instrument
}

sealed class BandResult {
    data class Success(val band: Band) : BandResult()
    data class Failure(val message: String) : BandResult()
}

/** 밴드 이름·초대 코드 규칙. 화면과 저장소가 같은 규칙을 쓰도록 한곳에 모은다. */
object BandRules {
    const val NAME_MAX = 20
    const val CODE_LENGTH = 6

    // 헷갈리기 쉬운 0/O, 1/I/L은 뺀다.
    const val CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    /** 문제가 없으면 null, 있으면 화면에 보여줄 메시지. */
    fun validateName(raw: String): String? {
        val name = raw.trim()
        return when {
            name.isEmpty() -> "밴드 이름을 입력해 주세요"
            name.length > NAME_MAX -> "밴드 이름은 ${NAME_MAX}자까지 쓸 수 있어요"
            else -> null
        }
    }

    /** 공백과 하이픈을 지우고 대문자로 바꾼다. "band-33" → "BAND33" */
    fun normalizeCode(raw: String): String =
        raw.filter { !it.isWhitespace() && it != '-' }.uppercase()

    fun validateCode(raw: String): String? {
        val code = normalizeCode(raw)
        return when {
            code.isEmpty() -> "초대 코드를 입력해 주세요"
            code.length != CODE_LENGTH || code.any { it !in CODE_CHARS } -> "초대 코드는 영문·숫자 ${CODE_LENGTH}자리예요"
            else -> null
        }
    }

    fun newCode(random: Random = Random.Default): String =
        (1..CODE_LENGTH).map { CODE_CHARS[random.nextInt(CODE_CHARS.length)] }.joinToString("")
}
