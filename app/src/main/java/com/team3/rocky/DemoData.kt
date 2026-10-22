package com.team3.rocky

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.core.content.FileProvider
import com.team3.rocky.auth.AuthRepository
import java.io.File

/*
 * ROCKY Iteration 2 시연 설정
 * - 실제 모델 연결 없이, app/src/main/assets/demo/ 에 넣어둔 결과 파일을 보여줍니다.
 * - 파일 이름 규칙: <악기>.png(악보 이미지), <악기>.mp3(악기 음원), <악기>.mid, <악기>.pdf,
 *   original.mp3(원곡), band.mid / band.pdf(밴드 전체, 선택)
 *   악기 이름: piano, drums, bass, guitar
 */
object Demo {
    const val DIR = "demo"

    // 결과 화면 파일 이름: band.png(또는 band-1.png, band-2.png …), band.mp3, band.pdf, band.mid
    const val BAND = "band"
    const val SONG_TITLE = "데모 곡 (Immigrant Song - Led Zeppelin)"

    // 화면에 보이는 순서
    val INSTRUMENTS = listOf("piano", "drums", "bass", "guitar")

    // 원곡에 없어서 AI가 새로 만든 악기 → 결과 화면에 'AI 생성' 표시
    val AI_GENERATED = setOf("piano")

    fun kor(i: String) = korName(i)

    fun emoji(i: String) = when (i) {
        "piano" -> "🎹"; "drums" -> "🥁"; "bass" -> "🎵"; "guitar" -> "🎸"; else -> "🎶"
    }
}

// ---------- 저장한 작업 (보관함) ----------
// Work 데이터와 저장 형식(WorkCodec)은 RockyLogic.kt에 있습니다.
object WorkStore {
    private const val PREF = "rocky"

    // 보관함은 회원마다 따로 저장한다. 로그인 전에는 쓰지 않는다.
    private fun key(ctx: Context) = workKey(AuthRepository.currentUserId(ctx))

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    fun load(ctx: Context): List<Work> = WorkCodec.decode(prefs(ctx).getString(key(ctx), ""))

    fun add(ctx: Context, w: Work) {
        val raw = WorkCodec.encode(WorkCodec.upsert(load(ctx), w))
        prefs(ctx).edit().putString(key(ctx), raw).apply()
    }

    /** 테스트용: 모든 회원의 보관함 비우기 */
    fun clear(ctx: Context) {
        prefs(ctx).edit().clear().commit()
    }
}

// ---------- 데모 파일 ----------
object Assets {
    fun list(ctx: Context): List<String> = ctx.assets.list(Demo.DIR)?.toList() ?: emptyList()

    fun find(ctx: Context, base: String, exts: List<String>): String? = findAsset(list(ctx), base, exts)

    /** assets 안의 파일을 캐시 폴더로 복사 (재생·공유용) */
    fun toCache(ctx: Context, name: String): File {
        val dir = File(ctx.cacheDir, "share").apply { mkdirs() }
        val out = File(dir, name)
        ctx.assets.open("${Demo.DIR}/$name").use { input ->
            out.outputStream().use { input.copyTo(it) }
        }
        return out
    }
}

fun displayName(ctx: Context, uri: Uri): String {
    var name = "업로드한 곡"
    ctx.contentResolver.query(uri, null, null, null, null)?.use { c ->
        val i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (i >= 0 && c.moveToFirst()) name = c.getString(i) ?: name
    }
    return name.substringBeforeLast('.')
}

/** 선택한 파일들을 카카오톡·메일·드라이브 등으로 공유 */
fun shareFiles(ctx: Context, names: List<String>) {
    if (names.isEmpty()) return
    val uris = ArrayList<Uri>(names.map {
        FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", Assets.toCache(ctx, it))
    })
    val intent = if (uris.size == 1) {
        Intent(Intent.ACTION_SEND).apply {
            type = mimeOf(names[0])
            putExtra(Intent.EXTRA_STREAM, uris[0])
        }
    } else {
        Intent(Intent.ACTION_SEND_MULTIPLE).apply {
            type = "*/*"
            putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
        }
    }
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    ctx.startActivity(Intent.createChooser(intent, "ROCKY 악보 공유"))
}
