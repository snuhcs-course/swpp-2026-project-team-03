package com.team3.rocky

/*
 * 안드로이드에 의존하지 않는 순수 로직 (Data/Logic 계층)
 * - 여기 있는 함수는 에뮬레이터 없이 JUnit만으로 테스트합니다 (app/src/test).
 * - DemoData.kt(WorkStore, Assets)와 RockyApp.kt(화면)는 이 함수들을 불러 씁니다.
 */

// ---------- 저장한 작업 ----------
data class Work(val id: Long, val title: String, val instruments: List<String>, val date: String)

val AUDIO_EXT = listOf("mp3", "wav", "flac", "ogg", "m4a")
val IMG_EXT = listOf("png", "jpg", "jpeg", "webp")

/** 악기 영문 이름 → 화면에 보이는 한글 이름 */
fun korName(inst: String): String = when (inst) {
    "piano" -> "피아노"
    "drums" -> "드럼"
    "bass" -> "베이스"
    "guitar" -> "기타"
    else -> inst
}

/**
 * 작업 목록 ↔ 저장 문자열 변환.
 * 한 줄에 작업 하나: id \t 제목 \t 악기1,악기2 \t 날짜
 */
object WorkCodec {
    private fun clean(s: String) = s.replace("\t", " ").replace("\r", " ").replace("\n", " ")

    fun encode(works: List<Work>): String = works.joinToString("\n") {
        "${it.id}\t${clean(it.title)}\t${it.instruments.joinToString(",")}\t${clean(it.date)}"
    }

    /** 비어 있거나 손상된 줄은 건너뜁니다. */
    fun decode(raw: String?): List<Work> {
        if (raw.isNullOrBlank()) return emptyList()
        return raw.split("\n").filter { it.isNotBlank() }.mapNotNull { line ->
            val p = line.split("\t")
            val id = p.getOrNull(0)?.toLongOrNull()
            if (p.size < 4 || id == null) null
            else Work(id, p[1], p[2].split(",").filter { it.isNotBlank() }, p[3])
        }
    }

    /** 새 작업을 맨 앞에 넣고, 같은 id의 예전 작업은 지웁니다. */
    fun upsert(works: List<Work>, w: Work): List<Work> = listOf(w) + works.filter { it.id != w.id }
}

/** 보관함은 회원마다 따로 저장합니다. 로그인 전이면 guest 칸을 씁니다. */
fun workKey(userId: Long?): String = "works_" + (userId ?: "guest")

// ---------- 데모 결과 파일 ----------
/** files 중에서 base.확장자 파일을 exts 순서대로 찾습니다. 없으면 null. */
fun findAsset(files: List<String>, base: String, exts: List<String>): String? =
    exts.map { "$base.$it" }.firstOrNull { it in files }

/**
 * 악보 이미지 파일을 페이지 순서대로 돌려줍니다.
 * base는 "band"(밴드 전체) 또는 악기 이름("piano", "bass" …).
 * base.png 하나 또는 MuseScore가 나눠 저장한 base-1.png, base-2.png, … base-10.png
 */
fun scorePageFiles(files: List<String>, base: String): List<String> {
    val re = Regex(
        "^${Regex.escape(base)}(-(\\d+))?\\.(${IMG_EXT.joinToString("|")})$",
        RegexOption.IGNORE_CASE,
    )
    return files
        .mapNotNull { n -> re.find(n)?.let { m -> (m.groupValues[2].toIntOrNull() ?: 0) to n } }
        .sortedWith(compareBy({ it.first }, { it.second }))
        .map { it.second }
}

/** 내보내기 화면에 보여줄 파일 (파일 이름 to 표시 이름). 실제로 있는 파일만. */
fun exportFiles(files: List<String>, base: String): List<Pair<String, String>> =
    listOf("$base.pdf" to "밴드 악보", "$base.mid" to "밴드 MIDI").filter { it.first in files }

/** 공유할 때 쓰는 파일 형식(MIME) */
fun mimeOf(name: String): String = when (name.substringAfterLast('.', "").lowercase()) {
    "pdf" -> "application/pdf"
    "mid", "midi" -> "audio/midi"
    "png" -> "image/png"
    else -> "*/*"
}
