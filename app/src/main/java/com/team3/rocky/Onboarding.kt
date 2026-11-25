// AI-generated with Claude Code, 2026-11-13
package com.team3.rocky

import androidx.compose.foundation.layout.widthIn
import android.app.Activity
import android.content.Context
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.launch

/**
 * 처음 켤 때 한 번 보는 것들: 이용 약관 동의(동의해야 앱을 쓸 수 있다)와 사용 안내 슬라이드.
 * 이 휴대폰에 저장한다 (회원과 상관없이 기기마다 한 번).
 */
object FirstRun {
    private const val PREF = "rocky_first_run"
    /** 약관 문구를 바꾸면 올린다. 올리면 모두 다시 동의해야 한다. */
    const val TERMS_VERSION = 2  // 2: 이용 목적(서비스 품질 개선)·듣기 24시간 추가 (11/25 베타)
    private const val KEY_TERMS = "terms_version"
    private const val KEY_GUIDE_OFF = "guide_never"

    /** 이번에 앱을 켠 뒤 안내를 이미 봤는지. 처음 안내는 처음 한 번만 저절로 뜬다 (2차 UAT: '다시 보지 않기' 없음). */
    var guideShownThisRun = false

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
    fun termsAgreed(ctx: Context) = prefs(ctx).getInt(KEY_TERMS, 0) >= TERMS_VERSION
    fun agreeTerms(ctx: Context) = prefs(ctx).edit().putInt(KEY_TERMS, TERMS_VERSION).apply()
    fun guideOff(ctx: Context) = prefs(ctx).getBoolean(KEY_GUIDE_OFF, false)
    fun setGuideOff(ctx: Context) = prefs(ctx).edit().putBoolean(KEY_GUIDE_OFF, true).apply()
}

/** 약관 한 조항. */
internal class TermsItem(val title: String, val body: String)

/** ROCKY 이용 약관 (처음 켤 때 화면과 회원가입의 '서비스 이용약관' 보기에서 같이 쓴다). */
internal fun termsItems() = listOf(
    TermsItem(
        tr("1. 개인 연습용으로만 써 주세요", "1. Personal practice only"),
        tr(
            "ROCKY로 만든 악보와 음원은 개인이나 동아리의 연습에만 쓸 수 있어요. 판매, 유료 배포, 광고, 공연·영상 수익 같은 상업적인 용도로는 쓸 수 없어요.",
            "Scores and audio made with ROCKY are for personal or club practice only. Don't sell them, distribute them for money, or use them in ads or paid performances and videos.",
        ),
    ),
    TermsItem(
        tr("2. 올리는 곡과 결과물의 책임은 사용자에게 있어요", "2. You are responsible for what you upload and how you use it"),
        tr(
            "직접 가지고 있거나 쓸 권리가 있는 음원만 올려 주세요. 곡을 올리고 만든 악보를 쓰고 나누는 데서 생기는 저작권 등 모든 책임은 사용자에게 있어요.",
            "Upload only audio you own or have the right to use. You are responsible for any copyright or other issues from uploading songs and using or sharing the scores.",
        ),
    ),
    TermsItem(
        tr("3. ROCKY는 채보를 돕는 도구예요", "3. ROCKY is a transcription aid"),
        tr(
            "악보는 올린 곡을 바탕으로 자동으로 옮겨 적은 것이고, 곡의 저작권은 원래 권리자에게 있어요. ROCKY는 새 작품을 창작하거나 곡에 대한 권리를 주장하지 않아요. 원곡에 없는 악기를 AI로 만든 파트(✨)도 원곡을 바탕으로 연습을 돕기 위한 것이에요.",
            "Scores are automatic transcriptions of the song you upload, and the song's copyright stays with its owners. ROCKY doesn't create new works or claim any rights in the song. AI-made parts (✨) are also based on the song and only meant to help you practice.",
        ),
    ),
    TermsItem(
        tr("4. 악보가 정확하지 않을 수 있어요", "4. Scores may contain mistakes"),
        tr(
            "자동으로 만든 악보라 틀린 음이나 박자가 있을 수 있어요. 연습하기 전에 원곡과 함께 확인해 주세요.",
            "Automatic scores can have wrong notes or rhythms. Please check them against the song.",
        ),
    ),
    TermsItem(
        tr("5. 파일은 이렇게 다뤄요", "5. How files are handled"),
        tr(
            "올린 곡 파일은 악보를 다 만들면 서버에서 지워요. 듣기용 음원(MP3)은 완성 후 24시간 동안만 두고 지워요. 만든 악보는 보관함과 밴드 공유를 위해 서버에 남고, 보관함에서 지우면 함께 지워져요 (밴드에 공유한 악보는 밴드에 남아요). 악보 파일은 휴대폰 밖으로 내보낼 수 없고 ROCKY 안에서만 볼 수 있어요.",
            "Uploaded song files are deleted from the server once the scores are made. Listening audio (MP3) is kept for 24 hours after a song is made, then deleted. Scores stay on the server for your library and band sharing, and go when you delete them from the library (scores shared with a band stay with the band). Scores can't be exported; you view them only in ROCKY.",
        ),
    ),
    TermsItem(
        tr("6. 이런 정보를 이런 목적으로 써요", "6. What we collect and why"),
        tr(
            "계정 정보(이메일·닉네임·프로필 사진)는 로그인과 밴드 기능에, 올린 곡과 만든 악보는 악보 만들기·보관함·밴드 공유에 써요. 또 서비스 품질 개선(작업 기록·별점 분석)을 위해 곡마다 만든 시간·결과·실패 이유 같은 작업 기록과 별점·의견을 계정과 함께 모아 분석해요.",
            "Account details (email, nickname, profile photo) are used for sign-in and bands, and your uploads and scores for making scores, your library and band sharing. To improve the service (analysing job records and ratings), we also collect each song's job record, such as processing time, result and failure reason, together with your ratings and comments, linked to your account.",
        ),
    ),
)

/**
 * 처음 켤 때 보는 이용 약관. 동의해야 앱을 쓸 수 있고, '동의하지 않음'이면 앱을 닫는다.
 */
@Composable
fun TermsScreen(onAgree: () -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    var checked by remember { mutableStateOf(false) }
    Surface(Modifier.fillMaxSize(), color = cs.background) {
        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(horizontal = 24.dp)) {
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                Spacer(Modifier.height(28.dp))
                Text("ROCKY", fontSize = 30.sp, fontWeight = FontWeight.ExtraBold, color = cs.primary, letterSpacing = (-0.5).sp)
                Spacer(Modifier.height(10.dp))
                Text(tr("시작하기 전에 확인해 주세요", "Before you get started"),
                    fontSize = 26.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(tr("ROCKY 이용 약관이에요.\n동의해야 앱을 쓸 수 있어요.", "These are ROCKY's terms of use.\nYou need to agree to use the app."),
                    fontSize = 14.sp, color = cs.onSurfaceVariant, lineHeight = 20.sp)
                Spacer(Modifier.height(20.dp))
                termsItems().forEach { item ->
                    Column(Modifier.fillMaxWidth().padding(bottom = 18.dp)) {
                        Text(item.title, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.height(4.dp))
                        Text(item.body, fontSize = 14.sp, lineHeight = 21.sp, color = cs.onSurfaceVariant)
                    }
                }
                Spacer(Modifier.height(4.dp))
            }
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).clickable { checked = !checked }
                    .padding(vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(checked = checked, onCheckedChange = { checked = it })
                Text(tr("위 내용을 모두 읽었고 동의해요", "I've read and agree to all of the above"),
                    fontSize = 15.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth().padding(bottom = 20.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    shape = ButtonShape, onClick = { (ctx as? Activity)?.finish() },
                    modifier = Modifier.weight(1f).height(54.dp),
                ) { Text(tr("동의하지 않음", "Don't agree"), maxLines = 1) }
                Button(
                    shape = ButtonShape, onClick = onAgree, enabled = checked,
                    modifier = Modifier.weight(1.4f).height(54.dp),
                ) { Text(tr("동의하고 시작하기", "Agree and start"), fontWeight = FontWeight.Bold, maxLines = 1) }
            }
        }
    }
}

/** 안내 그림 칸 높이 (모든 장 같음). */
private val GUIDE_ART = 190.dp

/** 안내 슬라이드 한 장. */
private class GuideSlide(val title: String, val body: String, val art: DrawScope.(Color, Color) -> Unit)

private fun guideSlides() = listOf(
    GuideSlide(
        tr("연습 방식과 악기를 골라요", "Pick how you practice"),
        tr("혼자 연습할 땐 '개인 연습용'으로 내 악기만, 합주할 땐 '밴드 합주용'으로 우리 밴드 악기를 골라요.", "Solo practice: just your instruments. Band rehearsal: every instrument in your band."),
    ) { fg, soft -> artBand(fg, soft) },
    GuideSlide(
        tr("곡을 올려요", "Upload the song"),
        tr("MP3·WAV·FLAC·OGG 파일을 고르면 끝이에요.\n원곡에 어떤 악기가 있는지는 ROCKY가 들어 보고 알아서 판단해요.", "Pick an MP3, WAV, FLAC or OGG file and you're done.\nROCKY listens and works out the song's instruments."),
    ) { fg, soft -> artUpload(fg, soft) },
    GuideSlide(
        tr("ROCKY가 당신을 위한 악보를 만들어요", "ROCKY makes scores just for you"),
        tr("다른 앱을 써도 ROCKY가 계속 만들어요.\n다 되거나 문제가 생기면 알림으로 알려 드려요.", "Use other apps while ROCKY works.\nWe'll notify you when it's done or if something goes wrong."),
    ) { fg, soft -> artBackground(fg, soft) },
    GuideSlide(
        tr("악보를 받아요", "Get your scores"),
        tr("원곡에 있는 파트는 그대로 옮기고, 없는 파트는 AI가 만들어요(✨). 밴드 합주용 악보는 밴드와 함께 볼 수 있어요.", "Parts in the song are transcribed; missing parts are made with AI (✨). Share band scores with your band to view together."),
    ) { fg, soft -> artScores(fg, soft) },
)

/**
 * 사용 안내 슬라이드. 처음 켤 때 한 번만 저절로 뜨고, 그다음은 홈 '이렇게 만들어요'의 '처음 안내 다시 보기'로 본다.
 * '다시 보지 않기'는 없다 (2차 UAT): 한 번 닫으면 다음부터 저절로 뜨지 않는다.
 */
@Composable
fun OnboardingDialog(onDone: () -> Unit) {
    val ctx = LocalContext.current
    val slides = remember { guideSlides() }
    GuideDialog(slides, neverStart = false, showNever = false, onClose = { FirstRun.setGuideOff(ctx); onDone() })
}

/** 결과 화면을 처음 열 때 한 번 보여주는 사용 안내. 결과 화면 ⋮ 메뉴의 '사용법 보기'로 다시 본다. */
object ResultGuide {
    private const val PREF = "rocky_first_run"
    private const val KEY = "result_guide_seen"

    /** 이번에 앱을 켠 뒤 저절로 이미 띄웠는지 ('다시 보지 않기'를 끈 사람도 한 번 켤 때 한 번만). */
    var shownThisRun = false

    fun seen(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getBoolean(KEY, false)
    fun markSeen(ctx: Context, seen: Boolean = true) =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putBoolean(KEY, seen).apply()

    /** 악보 화면을 열 때 저절로 띄울지: 설치 뒤 처음 한 번만 ('다시 보지 않기'를 끄면 다음에 앱을 켤 때 한 번 더). */
    fun shouldAutoShow(ctx: Context) = !seen(ctx) && !shownThisRun
}

/** 결과 화면 사용 안내: 악기 고르기, 악보 넘기기·확대, 재생, 마디 따라가기, 키 바꾸기·전체 화면, 공유·별점. */
@Composable
fun ResultGuideDialog(personal: Boolean, auto: Boolean = false, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val slides = remember(personal) { resultGuideSlides(personal) }
    if (auto) {
        // 뜨는 순간 '봤다'로 기록한다. 닫기 전에 화면이 다시 만들어지거나(언어·다크 모드 변경 등)
        // 앱이 꺼져도 곡을 열 때마다 다시 뜨지 않게 (2차 UAT).
        LaunchedEffect(Unit) { ResultGuide.shownThisRun = true; ResultGuide.markSeen(ctx) }
        // 저절로 뜰 때만 '다시 보지 않기'(기본 체크). 끄고 닫으면 다음에 앱을 켤 때 한 번 더 뜬다.
        GuideDialog(slides, neverStart = true, showNever = true, onClose = { never -> ResultGuide.markSeen(ctx, never); onDone() })
    } else {
        // ⋮ 메뉴 '사용법 보기'로 다시 볼 때는 체크 칸 없이.
        GuideDialog(slides, neverStart = false, showNever = false, onClose = { onDone() })
    }
}

private fun resultGuideSlides(personal: Boolean) = listOf(
    if (personal) GuideSlide(
        tr("연습할 악기의 악보예요", "Your instrument's score"),
        tr("곡 이름 뒤에 연습할 악기가 붙어 있어요.\n원곡에 없어서 AI가 만든 악보면 ✨가 보여요.\n기타 2대로 만들었으면 위에서 기타 1·기타 2를 골라 봐요.",
            "The song name ends with your instrument. ✨ means it isn't in the song and was made with AI. If you made two guitars, pick Guitar 1 or 2 at the top."),
    ) { fg, soft -> artParts(fg, soft) } else GuideSlide(
        tr("악기를 골라 듣고 봐요", "Pick a part to see and hear"),
        tr("위에서 악기를 누르면 그 악기의 악보와 소리만 나와요.\n'전체'는 밴드 전체예요.\n회색은 이 곡에 없는 악기, ✨는 AI가 만든 파트예요.",
            "Tap an instrument for its score and sound; 'All' is the whole band.\nGrey ones aren't in this song, ✨ marks AI-made parts."),
    ) { fg, soft -> artParts(fg, soft) },
    GuideSlide(
        tr("악보는 옆으로 넘겨요", "Swipe through the score"),
        tr("한 쪽씩 좌우로 넘기고, 두 손가락으로 벌리면 크게 볼 수 있어요.\n아래 쪽 번호를 누르면 원하는 쪽으로 가고, 꾹 누른 채 옆으로 밀면 빠르게 넘겨요.",
            "Swipe page by page and pinch to zoom.\nTap the page number to jump to a page, or press and hold it and slide to flip fast."),
    ) { fg, soft -> artPages(fg, soft) },
    GuideSlide(
        tr("연주 중인 마디를 따라가요", "Follow the playing bar"),
        tr("재생하면 지금 연주하는 마디에 색이 칠해지고 악보가 알아서 넘어가요.\n오른쪽 위 ⋮ 메뉴에서 끄고 켤 수 있어요.",
            "While playing, the current bar is highlighted and pages turn by themselves.\nTurn it on or off in the ⋮ menu."),
    ) { fg, soft -> artFollow(fg, soft) },
    GuideSlide(
        tr("키 바꾸기와 전체 화면", "Change key, full screen"),
        tr("⋮ 메뉴에서 반 키·한 키씩 키를 바꾸면 악보와 소리를 새 키로 다시 만들어요.\n악보 오른쪽 위 버튼으로 전체 화면을 켜요.",
            "Change the key by half or whole steps in the ⋮ menu; scores and audio are remade.\nThe button on the score opens full screen."),
    ) { fg, soft -> artKey(fg, soft) },
    GuideSlide(
        if (personal) tr("악보를 평가해 주세요", "Rate the score") else tr("밴드와 함께 보고 평가해요", "Share and rate"),
        if (personal) tr("악보는 보관함에 자동으로 저장돼요.\n마지막 쪽 다음 장에서 별점과 의견을 남기면 ROCKY가 더 좋아져요.",
            "Scores are saved to your library automatically.\nRate it on the page after the last one to help ROCKY improve.")
        else tr("악보는 보관함에 자동으로 저장되고, ⋮ 메뉴의 '밴드에 공유'로 멤버와 함께 봐요.\n마지막 쪽 다음 장에서 별점을 남겨 주세요.",
            "Scores are saved to your library automatically.\nUse 'Share with a band' in the ⋮ menu, and rate it after the last page."),
    ) { fg, soft -> artRate(fg, soft) },
)

/** 안내 슬라이드 창 (처음 안내·결과 화면 안내가 같이 쓴다). */
@Composable
private fun GuideDialog(slides: List<GuideSlide>, neverStart: Boolean, showNever: Boolean, onClose: (never: Boolean) -> Unit) {
    val cs = MaterialTheme.colorScheme
    val pager = rememberPagerState { slides.size }
    val scope = rememberCoroutineScope()
    var never by remember { mutableStateOf(neverStart) }
    fun close() = onClose(never)
    // 모든 장이 같은 크기로 보이게: 창 너비는 최대 360dp, 그림·제목(2줄)·설명(4줄) 칸 높이를 고정한다.
    Dialog(onDismissRequest = { close() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(
            Modifier.padding(horizontal = 20.dp).widthIn(max = 360.dp).fillMaxWidth(),
            shape = RoundedCornerShape(28.dp), color = cs.surface,
        ) {
            Column(Modifier.padding(top = 8.dp, bottom = 18.dp)) {
                Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("${pager.currentPage + 1} / ${slides.size}", fontSize = 13.sp, color = cs.onSurfaceVariant, modifier = Modifier.weight(1f))
                    TextButton(onClick = { close() }) { Text(tr("건너뛰기", "Skip"), color = cs.onSurfaceVariant) }
                }
                HorizontalPager(state = pager, modifier = Modifier.fillMaxWidth()) { i ->
                    val slide = slides[i]
                    Column(Modifier.fillMaxWidth().padding(horizontal = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Box(
                            Modifier.fillMaxWidth().height(GUIDE_ART).clip(RoundedCornerShape(24.dp))
                                .background(Brush.verticalGradient(listOf(cs.primary.copy(alpha = 0.20f), cs.primary.copy(alpha = 0.06f)))),
                            contentAlignment = Alignment.Center,
                        ) {
                            val fg = cs.primary
                            val soft = cs.onSurface
                            Canvas(Modifier.size(GUIDE_ART - 30.dp).semantics { contentDescription = slide.title }) { slide.art(this, fg, soft) }
                        }
                        Spacer(Modifier.height(20.dp))
                        // 모든 장의 제목·설명을 투명하게 겹쳐 두어 가장 긴 장에 맞춰 칸 높이를 잡는다.
                        // 그래서 넘겨도 창 크기가 그대로이고, 글자를 크게 쓰는 폰(S23 Ultra 등)에서도 잘리지 않는다.
                        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                            slides.forEach { GuideTitle(it.title, Modifier.alpha(0f)) }
                            GuideTitle(slide.title)
                        }
                        Spacer(Modifier.height(6.dp))
                        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.TopCenter) {
                            slides.forEach { GuideBody(it.body, Modifier.alpha(0f)) }
                            GuideBody(slide.body)
                        }
                    }
                }
                // 몇 번째 장인지 점으로
                Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.Center) {
                    repeat(slides.size) { i ->
                        val on = i == pager.currentPage
                        Box(
                            Modifier.padding(horizontal = 3.dp).height(6.dp).width(if (on) 18.dp else 6.dp)
                                .clip(CircleShape).background(if (on) cs.primary else cs.outlineVariant),
                        )
                    }
                }
                Spacer(Modifier.height(16.dp))
                Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                    if (showNever) Row(
                        Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).clickable { never = !never },
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Checkbox(checked = never, onCheckedChange = { never = it })
                        Text(tr("다시 보지 않기", "Don't show again"), fontSize = 13.sp, color = cs.onSurfaceVariant)
                    } else Spacer(Modifier.weight(1f))
                    val last = pager.currentPage == slides.lastIndex
                    // '다음'과 '시작하기'가 같은 너비라 마지막 장에서도 버튼이 움직이지 않는다.
                    Button(
                        shape = ButtonShape,
                        onClick = { if (last) close() else scope.launch { pager.animateScrollToPage(pager.currentPage + 1) } },
                        modifier = Modifier.height(48.dp).width(116.dp),
                        contentPadding = TightButtonPadding,
                    ) { Text(if (last) tr("시작하기", "Start") else tr("다음", "Next"), fontWeight = FontWeight.Bold, maxLines = 1) }
                }
            }
        }
    }
}

// ----- 안내 그림 (170dp 칸에 24칸 격자 대신 100칸 격자로 그린다) -----
private fun DrawScope.unit() = size.minDimension / 100f

/** 1. 무대 위 악기 세 개: 주황 원 안에 드럼·기타·베이스 모양. */
private fun DrawScope.artBand(fg: Color, soft: Color) {
    val u = unit()
    val stroke = Stroke(2.6f * u, cap = StrokeCap.Round, join = StrokeJoin.Round)
    // 무대 바닥
    drawRoundRect(soft.copy(alpha = 0.10f), Offset(6 * u, 72 * u), Size(88 * u, 14 * u), CornerRadius(7 * u))
    listOf(Offset(24 * u, 52 * u), Offset(50 * u, 40 * u), Offset(76 * u, 52 * u)).forEachIndexed { i, c ->
        val r = if (i == 1) 19 * u else 15 * u
        drawCircle(fg, r, c)
        val w = Color.White
        when (i) {
            0 -> { // 기타: 몸통 두 원 + 목
                drawCircle(w, 4.2f * u, Offset(c.x - 2 * u, c.y + 3 * u), style = stroke)
                drawCircle(w, 3.2f * u, Offset(c.x + 1.5f * u, c.y - 1.5f * u), style = stroke)
                drawLine(w, Offset(c.x + 3 * u, c.y - 3 * u), Offset(c.x + 9 * u, c.y - 9 * u), stroke.width, StrokeCap.Round)
            }
            1 -> { // 드럼: 타원 북 + 스틱
                drawOval(w, Offset(c.x - 10 * u, c.y - 4 * u), Size(20 * u, 6 * u), style = stroke)
                drawLine(w, Offset(c.x - 10 * u, c.y - 1 * u), Offset(c.x - 10 * u, c.y + 7 * u), stroke.width, StrokeCap.Round)
                drawLine(w, Offset(c.x + 10 * u, c.y - 1 * u), Offset(c.x + 10 * u, c.y + 7 * u), stroke.width, StrokeCap.Round)
                drawArc(w, 0f, 180f, false, Offset(c.x - 10 * u, c.y + 4 * u), Size(20 * u, 6 * u), style = stroke)
                drawLine(w, Offset(c.x - 6 * u, c.y - 12 * u), Offset(c.x - 1 * u, c.y - 4 * u), stroke.width, StrokeCap.Round)
                drawLine(w, Offset(c.x + 6 * u, c.y - 12 * u), Offset(c.x + 1 * u, c.y - 4 * u), stroke.width, StrokeCap.Round)
            }
            else -> { // 건반
                drawRoundRect(w, Offset(c.x - 9 * u, c.y - 5 * u), Size(18 * u, 10 * u), CornerRadius(2 * u), style = stroke)
                for (k in 0..2) drawLine(w, Offset(c.x - 4.5f * u + k * 4.5f * u, c.y - 5 * u), Offset(c.x - 4.5f * u + k * 4.5f * u, c.y + 5 * u), 1.8f * u)
            }
        }
    }
    // 고른 표시 ✓
    drawCircle(Color.White, 6 * u, Offset(64 * u, 26 * u))
    drawCircle(fg, 6 * u, Offset(64 * u, 26 * u), style = Stroke(1.6f * u))
    val check = Path().apply { moveTo(61 * u, 26 * u); lineTo(63.3f * u, 28.5f * u); lineTo(67.3f * u, 23.5f * u) }
    drawPath(check, fg, style = Stroke(2f * u, cap = StrokeCap.Round, join = StrokeJoin.Round))
}

/** 2. 음악 파일 + 위로 올리는 화살표. */
private fun DrawScope.artUpload(fg: Color, soft: Color) {
    val u = unit()
    val s = Stroke(3f * u, cap = StrokeCap.Round, join = StrokeJoin.Round)
    // 파일 (오른쪽 위 접힌 모서리)
    val file = Path().apply {
        moveTo(26 * u, 12 * u); lineTo(58 * u, 12 * u); lineTo(74 * u, 28 * u); lineTo(74 * u, 86 * u)
        lineTo(26 * u, 86 * u); close()
    }
    drawPath(file, soft.copy(alpha = 0.08f))
    drawPath(file, soft.copy(alpha = 0.55f), style = s)
    drawPath(Path().apply { moveTo(58 * u, 12 * u); lineTo(58 * u, 28 * u); lineTo(74 * u, 28 * u) }, soft.copy(alpha = 0.55f), style = s)
    // 음표
    drawCircle(fg, 6 * u, Offset(42 * u, 62 * u))
    drawLine(fg, Offset(47.5f * u, 62 * u), Offset(47.5f * u, 38 * u), 3f * u, StrokeCap.Round)
    drawLine(fg, Offset(47.5f * u, 38 * u), Offset(58 * u, 42 * u), 3f * u, StrokeCap.Round)
    // 올리는 화살표 (주황 원)
    drawCircle(fg, 13 * u, Offset(74 * u, 76 * u))
    drawLine(Color.White, Offset(74 * u, 83 * u), Offset(74 * u, 69 * u), 3f * u, StrokeCap.Round)
    drawPath(Path().apply { moveTo(68 * u, 74 * u); lineTo(74 * u, 68 * u); lineTo(80 * u, 74 * u) }, Color.White,
        style = Stroke(3f * u, cap = StrokeCap.Round, join = StrokeJoin.Round))
}

/** 3. 휴대폰 위의 진행 고리와 알림 종. */
private fun DrawScope.artBackground(fg: Color, soft: Color) {
    val u = unit()
    val s = Stroke(3f * u, cap = StrokeCap.Round, join = StrokeJoin.Round)
    drawRoundRect(soft.copy(alpha = 0.08f), Offset(28 * u, 8 * u), Size(44 * u, 84 * u), CornerRadius(8 * u))
    drawRoundRect(soft.copy(alpha = 0.55f), Offset(28 * u, 8 * u), Size(44 * u, 84 * u), CornerRadius(8 * u), style = s)
    drawLine(soft.copy(alpha = 0.55f), Offset(44 * u, 15 * u), Offset(56 * u, 15 * u), 2.4f * u, StrokeCap.Round)
    // 진행 고리 70%
    drawCircle(soft.copy(alpha = 0.15f), 14 * u, Offset(50 * u, 48 * u), style = Stroke(5f * u))
    drawArc(fg, -90f, 252f, false, Offset(36 * u, 34 * u), Size(28 * u, 28 * u), style = Stroke(5f * u, cap = StrokeCap.Round))
    // 아래 막대 (다른 앱 화면)
    drawRoundRect(soft.copy(alpha = 0.18f), Offset(35 * u, 70 * u), Size(30 * u, 5 * u), CornerRadius(2.5f * u))
    drawRoundRect(soft.copy(alpha = 0.18f), Offset(35 * u, 79 * u), Size(20 * u, 5 * u), CornerRadius(2.5f * u))
    // 알림 종 (오른쪽 위 주황 원)
    val c = Offset(74 * u, 24 * u)
    drawCircle(fg, 13 * u, c)
    val bell = Path().apply {
        moveTo(c.x - 6 * u, c.y + 4 * u)
        cubicTo(c.x - 5 * u, c.y + 2 * u, c.x - 5 * u, c.y - 1 * u, c.x - 5 * u, c.y - 2 * u)
        cubicTo(c.x - 5 * u, c.y - 6 * u, c.x - 2.5f * u, c.y - 7.5f * u, c.x, c.y - 7.5f * u)
        cubicTo(c.x + 2.5f * u, c.y - 7.5f * u, c.x + 5 * u, c.y - 6 * u, c.x + 5 * u, c.y - 2 * u)
        cubicTo(c.x + 5 * u, c.y - 1 * u, c.x + 5 * u, c.y + 2 * u, c.x + 6 * u, c.y + 4 * u)
        close()
    }
    drawPath(bell, Color.White, style = Stroke(2.2f * u, join = StrokeJoin.Round))
    drawCircle(Color.White, 1.6f * u, Offset(c.x, c.y + 6.6f * u))
}

/** 4. 오선 악보 두 장(겹친 종이)과 반짝임. */
private fun DrawScope.artScores(fg: Color, soft: Color) {
    val u = unit()
    // 뒤 종이
    drawRoundRect(soft.copy(alpha = 0.12f), Offset(34 * u, 10 * u), Size(50 * u, 66 * u), CornerRadius(5 * u))
    // 앞 종이
    drawRoundRect(Color.White, Offset(18 * u, 22 * u), Size(52 * u, 68 * u), CornerRadius(5 * u))
    drawRoundRect(soft.copy(alpha = 0.25f), Offset(18 * u, 22 * u), Size(52 * u, 68 * u), CornerRadius(5 * u), style = Stroke(1.5f * u))
    val ink = Color(0xFF26262B)
    for (block in 0..1) {
        val top = 34 * u + block * 26 * u
        for (l in 0..4) drawLine(ink.copy(alpha = 0.55f), Offset(25 * u, top + l * 3.2f * u), Offset(63 * u, top + l * 3.2f * u), 0.9f * u)
        // 음표 몇 개
        listOf(31f, 40f, 49f, 58f).forEachIndexed { k, x ->
            val y = top + (if (k % 2 == 0) 9.6f else 3.2f) * u
            drawOval(if (block == 1 && k >= 2) fg else ink, Offset(x * u - 2.2f * u, y - 1.6f * u), Size(4.4f * u, 3.2f * u))
            drawLine(if (block == 1 && k >= 2) fg else ink, Offset(x * u + 2 * u, y), Offset(x * u + 2 * u, y - 9 * u), 1.1f * u)
        }
    }
    // 반짝임 ✨ (AI 파트)
    fun spark(cx: Float, cy: Float, r: Float) {
        val p = Path().apply {
            moveTo(cx, cy - r); quadraticTo(cx, cy, cx + r, cy); quadraticTo(cx, cy, cx, cy + r)
            quadraticTo(cx, cy, cx - r, cy); quadraticTo(cx, cy, cx, cy - r); close()
        }
        drawPath(p, fg)
    }
    spark(80 * u, 72 * u, 9 * u)
    spark(88 * u, 56 * u, 4.5f * u)
}




@Composable
private fun GuideTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, fontSize = 21.sp, lineHeight = 29.sp, fontWeight = FontWeight.ExtraBold,
        textAlign = TextAlign.Center, modifier = modifier.fillMaxWidth())
}

@Composable
private fun GuideBody(text: String, modifier: Modifier = Modifier) {
    Text(text, fontSize = 14.sp, lineHeight = 21.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
        textAlign = TextAlign.Center, modifier = modifier.fillMaxWidth())
}

// ----- 결과 화면 안내 그림 -----

/** 악기 칸 네 개 (하나는 골라짐, 하나는 회색). */
private fun DrawScope.artParts(fg: Color, soft: Color) {
    val u = unit()
    drawRoundRect(soft.copy(alpha = 0.18f), Offset(10 * u, 14 * u), Size(80 * u, 16 * u), CornerRadius(5 * u))
    val cells = listOf(Offset(10 * u, 36 * u), Offset(52 * u, 36 * u), Offset(10 * u, 58 * u), Offset(52 * u, 58 * u))
    cells.forEachIndexed { i, o ->
        val color = when (i) { 1 -> fg; 2 -> soft.copy(alpha = 0.07f); else -> soft.copy(alpha = 0.18f) }
        drawRoundRect(color, o, Size(38 * u, 16 * u), CornerRadius(5 * u))
    }
    // 누르는 손가락
    drawCircle(Color.White, 6 * u, Offset(78 * u, 50 * u))
    drawCircle(fg, 6 * u, Offset(78 * u, 50 * u), style = Stroke(1.6f * u))
    drawCircle(soft.copy(alpha = 0.18f), 12 * u, Offset(78 * u, 50 * u), style = Stroke(1.2f * u))
}

/** 악보 두 장과 넘기는 화살표. */
private fun DrawScope.artPages(fg: Color, soft: Color) {
    val u = unit()
    listOf(14f, 52f).forEachIndexed { i, x ->
        drawRoundRect(if (i == 0) Color.White else Color.White.copy(alpha = 0.6f), Offset(x * u, 14 * u), Size(34 * u, 48 * u), CornerRadius(3 * u))
        for (k in 0..3) for (l in 0..2) {
            val y = (22 + k * 10 + l * 2) * u
            drawLine(Color(0xFF555555), Offset((x + 4) * u, y), Offset((x + 30) * u, y), 0.6f * u)
        }
    }
    val arrow = Path().apply { moveTo(40 * u, 76 * u); lineTo(62 * u, 76 * u); moveTo(56 * u, 71 * u); lineTo(62 * u, 76 * u); lineTo(56 * u, 81 * u) }
    drawPath(arrow, fg, style = Stroke(3f * u, cap = StrokeCap.Round, join = StrokeJoin.Round))
}

/** 악보 한 장, 칠해진 마디, 아래 재생 막대. */
private fun DrawScope.artFollow(fg: Color, soft: Color) {
    val u = unit()
    drawRoundRect(Color.White, Offset(22 * u, 8 * u), Size(56 * u, 60 * u), CornerRadius(3 * u))
    for (k in 0..3) for (l in 0..2) {
        val y = (16 + k * 13 + l * 2.5f) * u
        drawLine(Color(0xFF555555), Offset(26 * u, y), Offset(74 * u, y), 0.6f * u)
    }
    drawRect(fg.copy(alpha = 0.25f), Offset(40 * u, 27 * u), Size(16 * u, 10 * u))
    drawRect(fg, Offset(40 * u, 36 * u), Size(16 * u, 1.6f * u))
    drawRoundRect(soft.copy(alpha = 0.18f), Offset(14 * u, 80 * u), Size(72 * u, 4 * u), CornerRadius(2 * u))
    drawRoundRect(fg, Offset(14 * u, 80 * u), Size(30 * u, 4 * u), CornerRadius(2 * u))
    drawCircle(fg, 4 * u, Offset(44 * u, 82 * u))
}

/** 위아래 화살표(키)와 전체 화면 모서리. */
private fun DrawScope.artKey(fg: Color, soft: Color) {
    val u = unit()
    val s = Stroke(3.2f * u, cap = StrokeCap.Round, join = StrokeJoin.Round)
    drawCircle(fg, 20 * u, Offset(32 * u, 50 * u))
    val up = Path().apply { moveTo(32 * u, 62 * u); lineTo(32 * u, 38 * u); moveTo(25 * u, 45 * u); lineTo(32 * u, 38 * u); lineTo(39 * u, 45 * u) }
    drawPath(up, Color.White, style = s)
    drawRoundRect(soft.copy(alpha = 0.18f), Offset(56 * u, 30 * u), Size(36 * u, 40 * u), CornerRadius(6 * u))
    val corners = Path().apply {
        moveTo(62 * u, 44 * u); lineTo(62 * u, 36 * u); lineTo(70 * u, 36 * u)
        moveTo(78 * u, 36 * u); lineTo(86 * u, 36 * u); lineTo(86 * u, 44 * u)
        moveTo(86 * u, 56 * u); lineTo(86 * u, 64 * u); lineTo(78 * u, 64 * u)
        moveTo(70 * u, 64 * u); lineTo(62 * u, 64 * u); lineTo(62 * u, 56 * u)
    }
    drawPath(corners, fg, style = s)
}

/** 별 다섯 개 (넷은 칠함). */
private fun DrawScope.artRate(fg: Color, soft: Color) {
    val u = unit()
    for (i in 0 until 5) {
        val c = Offset((14 + i * 18) * u, 50 * u)
        val star = Path().apply {
            for (k in 0 until 10) {
                val r = (if (k % 2 == 0) 8f else 3.4f) * u
                val a = Math.toRadians((-90 + k * 36).toDouble())
                val x = c.x + r * Math.cos(a).toFloat(); val y = c.y + r * Math.sin(a).toFloat()
                if (k == 0) moveTo(x, y) else lineTo(x, y)
            }
            close()
        }
        drawPath(star, if (i < 4) fg else soft.copy(alpha = 0.25f))
    }
}
