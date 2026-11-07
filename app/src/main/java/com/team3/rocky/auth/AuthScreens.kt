// AI-generated with Claude Code, 2026-10-15 (2026-11-03 수정: 실시간 입력 확인, 이메일 인증, 프로필 사진, 내 정보 수정)
package com.team3.rocky.auth

import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.team3.rocky.AppSettings
import com.team3.rocky.Avatar
import com.team3.rocky.Demo
import com.team3.rocky.InstrumentIcon
import com.team3.rocky.Lang
import com.team3.rocky.Page
import com.team3.rocky.ProfileStore
import com.team3.rocky.tr
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ---------- 로그인 ----------
@Composable
fun LoginScreen(auth: AuthRepository, onLoggedIn: (User) -> Unit, onSignUp: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    fun submit() {
        if (busy) return
        focus.clearFocus()
        busy = true
        error = null
        scope.launch {
            when (val r = auth.login(email, password)) {
                is AuthResult.Success -> onLoggedIn(r.user)
                is AuthResult.Failure -> error = r.message
                is AuthResult.Invalid -> error = r.errors.values.first()
            }
            busy = false
        }
    }

    Column(
        Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
    ) {
        // 로그인 전에도 언어를 바꿀 수 있게 오른쪽 위에 둔다.
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) { LanguageSwitch() }
        Spacer(Modifier.height(24.dp))
        Text("ROCKY", fontSize = 48.sp, fontWeight = FontWeight.Black, color = cs.primary)
        Text(tr("어떤 곡이든, 우리 밴드 악보로", "Any song, scored for your band"), fontSize = 16.sp, color = cs.onSurfaceVariant)
        Spacer(Modifier.height(40.dp))

        AuthField(
            value = email, onValueChange = { email = it; error = null }, label = tr("이메일", "Email"),
            keyboardType = KeyboardType.Email, tag = "login_email",
            onNext = { focus.moveFocus(FocusDirection.Down) },
        )
        Spacer(Modifier.height(12.dp))
        PasswordField(
            value = password, onValueChange = { password = it; error = null }, label = tr("비밀번호", "Password"),
            imeAction = ImeAction.Done, tag = "login_password", onDone = { submit() },
        )
        if (error != null) {
            Spacer(Modifier.height(10.dp))
            Text(error!!, color = cs.error, fontSize = 13.sp, modifier = Modifier.testTag("login_error"))
        }
        Spacer(Modifier.height(24.dp))
        Button(
            onClick = { submit() }, enabled = !busy,
            modifier = Modifier.fillMaxWidth().height(56.dp).testTag("login_submit"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = cs.onPrimary)
            else Text(tr("로그인", "Log in"), fontSize = 17.sp)
        }
        Spacer(Modifier.height(12.dp))
        OutlinedButton(
            onClick = onSignUp, enabled = !busy,
            modifier = Modifier.fillMaxWidth().height(52.dp).testTag("go_signup"),
        ) { Text(tr("이메일로 회원가입", "Sign up with email")) }
        Spacer(Modifier.height(16.dp))
        Text(
            tr("Google · Apple 로그인은 준비 중이에요", "Google and Apple sign-in are coming soon"),
            fontSize = 12.sp, color = cs.onSurfaceVariant, modifier = Modifier.fillMaxWidth(),
        )
    }
}

// ---------- 회원가입 ----------
@Composable
fun SignUpScreen(auth: AuthRepository, onBack: () -> Unit, onSignedUp: (User) -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    var form by remember { mutableStateOf(SignUpForm()) }
    // 가입하기를 누른 뒤에는 비어 있는 칸도 오류를 보여준다.
    var submitted by remember { mutableStateOf(false) }
    var serverErrors by remember { mutableStateOf<Map<SignUpValidator.Field, String>>(emptyMap()) }
    var failure by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var termsDialog by remember { mutableStateOf<Pair<String, String>?>(null) }

    // 이미 가입된 이메일·닉네임은 입력을 멈추면 바로 알려준다.
    var emailTaken by remember { mutableStateOf(false) }
    var nicknameTaken by remember { mutableStateOf(false) }
    LaunchedEffect(form.email) {
        emailTaken = false
        if (SignUpValidator.emailError(form.email) == null) { delay(300); emailTaken = auth.isEmailTaken(form.email) }
    }
    LaunchedEffect(form.nickname) {
        nicknameTaken = false
        if (SignUpValidator.nicknameError(form.nickname) == null) { delay(300); nicknameTaken = auth.isNicknameTaken(form.nickname) }
    }

    // 이메일 인증 (시연: 번호를 화면에 보여준다)
    val verification = remember { EmailVerification() }
    var codeSent by remember { mutableStateOf(false) }
    var code by remember { mutableStateOf("") }
    var verifiedEmail by remember { mutableStateOf<String?>(null) }
    var codeError by remember { mutableStateOf<String?>(null) }
    var shownCode by remember { mutableStateOf<String?>(null) }
    val verified = verifiedEmail != null && verifiedEmail == SignUpValidator.normalizeEmail(form.email)

    // 프로필 사진 (선택)
    var photoUri by remember { mutableStateOf<Uri?>(null) }
    var photo by remember { mutableStateOf<ImageBitmap?>(null) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) { photoUri = uri; photo = ProfileStore.preview(ctx, uri) }
    }

    fun show(value: String) = submitted || value.isNotEmpty()
    val emailErr = serverErrors[SignUpValidator.Field.EMAIL]
        ?: SignUpValidator.emailError(form.email)?.takeIf { show(form.email) }
        ?: tr("이미 가입된 이메일이에요", "This email is already registered").takeIf { emailTaken }
    val passwordErr = SignUpValidator.passwordError(form.password)?.takeIf { show(form.password) }
    val confirmErr = SignUpValidator.passwordConfirmError(form.password, form.passwordConfirm)
        ?.takeIf { show(form.passwordConfirm) }
    val nicknameErr = serverErrors[SignUpValidator.Field.NICKNAME]
        ?: SignUpValidator.nicknameError(form.nickname, typing = !submitted)?.takeIf { show(form.nickname) }
        ?: tr("이미 사용 중인 닉네임이에요", "This nickname is taken").takeIf { nicknameTaken }
    val agreementErr = SignUpValidator.agreementError(form).takeIf { submitted }

    fun edit(change: (SignUpForm) -> SignUpForm) {
        form = change(form)
        serverErrors = emptyMap()
        failure = null
    }

    fun sendCode() {
        if (SignUpValidator.emailError(form.email) != null || emailTaken) return
        shownCode = verification.send(form.email)
        codeSent = true
        code = ""
        codeError = null
    }

    fun checkCode() {
        codeError = verification.check(form.email, code)
        if (codeError == null) { verifiedEmail = SignUpValidator.normalizeEmail(form.email); focus.clearFocus() }
    }

    fun submit() {
        if (busy) return
        focus.clearFocus()
        submitted = true
        val local = SignUpValidator.validate(form)
        if (local.isNotEmpty() || emailTaken || nicknameTaken) return
        if (!verified) { codeError = tr("이메일 인증을 완료해 주세요", "Please verify your email"); return }
        busy = true
        scope.launch {
            when (val r = auth.signUp(form)) {
                is AuthResult.Success -> {
                    photoUri?.let { ProfileStore.save(ctx, r.user.id, it) }
                    onSignedUp(r.user)
                }
                is AuthResult.Invalid -> serverErrors = r.errors
                is AuthResult.Failure -> failure = r.message
            }
            busy = false
        }
    }

    Page(tr("회원가입", "Sign up"), onBack, dividers = true, bottom = {
        Button(
            onClick = { submit() }, enabled = !busy,
            modifier = Modifier.fillMaxWidth().height(56.dp).testTag("signup_submit"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = cs.onPrimary)
            else Text(tr("가입하기", "Sign up"), fontSize = 17.sp)
        }
    }) {
        Column(Modifier.fillMaxWidth().weight(1f).imePadding().verticalScroll(rememberScrollState())) {
            Spacer(Modifier.height(16.dp))
            Text(tr("ROCKY와 함께\n밴드 악보를 만들어요", "Make band scores\nwith ROCKY"), fontSize = 26.sp, fontWeight = FontWeight.Bold, lineHeight = 34.sp)
            Spacer(Modifier.height(24.dp))

            SectionLabel(tr("계정", "Account"))
            AuthField(
                value = form.email,
                onValueChange = { v -> edit { it.copy(email = v) }; codeError = null },
                label = tr("이메일", "Email"), keyboardType = KeyboardType.Email, tag = "signup_email",
                error = emailErr,
                hint = when {
                    verified -> tr("✓ 인증 완료", "✓ Verified")
                    form.email.isNotEmpty() -> tr("✓ 사용할 수 있는 이메일이에요", "✓ This email works")
                    else -> tr("로그인할 때 아이디로 써요", "You'll use this to log in")
                },
                trailing = {
                    TextButton(
                        onClick = { sendCode() },
                        enabled = !verified && SignUpValidator.emailError(form.email) == null && !emailTaken,
                    ) { Text(if (verified) tr("인증됨", "Verified") else if (codeSent) tr("다시 받기", "Resend") else tr("인증번호 받기", "Get code"), fontSize = 12.sp) }
                },
                onNext = { focus.moveFocus(FocusDirection.Down) },
            )
            if (codeSent && !verified) {
                Spacer(Modifier.height(8.dp))
                AuthField(
                    value = code, onValueChange = { code = it.filter(Char::isDigit).take(EmailVerification.CODE_LENGTH); codeError = null },
                    label = tr("인증번호 ${EmailVerification.CODE_LENGTH}자리", "${EmailVerification.CODE_LENGTH}-digit code"), keyboardType = KeyboardType.NumberPassword,
                    tag = "signup_code", error = codeError, hint = tr("메일로 받은 번호를 입력해 주세요 (5분 안에)", "Enter the code from your email (within 5 min)"),
                    trailing = { TextButton(onClick = { checkCode() }, enabled = code.length == EmailVerification.CODE_LENGTH) { Text(tr("확인", "OK")) } },
                    imeAction = ImeAction.Done, onDone = { checkCode() },
                )
            } else if (!codeSent && codeError != null) {
                Text(codeError!!, color = cs.error, fontSize = 12.sp, modifier = Modifier.padding(start = 16.dp))
            }
            Spacer(Modifier.height(8.dp))
            PasswordField(
                value = form.password, onValueChange = { v -> edit { it.copy(password = v) } },
                label = tr("비밀번호", "Password"), tag = "signup_password", error = passwordErr,
                hint = if (form.password.isNotEmpty()) tr("✓ 사용할 수 있는 비밀번호예요", "✓ Good password")
                else tr("영문과 숫자를 포함해 ${SignUpValidator.PASSWORD_MIN}자 이상", "${SignUpValidator.PASSWORD_MIN}+ characters with letters and numbers"),
                onNext = { focus.moveFocus(FocusDirection.Down) },
            )
            Spacer(Modifier.height(8.dp))
            PasswordField(
                value = form.passwordConfirm,
                onValueChange = { v -> edit { it.copy(passwordConfirm = v) } },
                label = tr("비밀번호 확인", "Confirm password"), tag = "signup_password_confirm", error = confirmErr,
                hint = if (form.passwordConfirm.isNotEmpty()) tr("✓ 비밀번호가 일치해요", "✓ Passwords match") else null,
                onNext = { focus.moveFocus(FocusDirection.Down) },
            )

            Spacer(Modifier.height(20.dp))
            SectionLabel(tr("프로필", "Profile"))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Avatar(photo, form.nickname, 64.dp, Modifier.clickable {
                    picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                })
                Spacer(Modifier.width(14.dp))
                Column {
                    Text(tr("프로필 사진 (선택)", "Profile photo (optional)"), fontWeight = FontWeight.Bold)
                    Row {
                        TextButton(onClick = {
                            picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                        }) { Text(if (photo == null) tr("사진 고르기", "Choose photo") else tr("다른 사진", "Change photo")) }
                        if (photo != null) TextButton(onClick = { photo = null; photoUri = null }) {
                            Text(tr("빼기", "Remove"), color = cs.onSurfaceVariant)
                        }
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
            AuthField(
                value = form.nickname, onValueChange = { v -> edit { it.copy(nickname = v) } },
                label = tr("닉네임", "Nickname"), tag = "signup_nickname", error = nicknameErr,
                hint = if (form.nickname.isNotEmpty()) tr("✓ 사용할 수 있는 닉네임이에요", "✓ This nickname works")
                else tr("${SignUpValidator.NICKNAME_MIN}~${SignUpValidator.NICKNAME_MAX}자, 한글·영문·숫자·_", "${SignUpValidator.NICKNAME_MIN}–${SignUpValidator.NICKNAME_MAX} characters: letters, numbers, _"),
                imeAction = ImeAction.Done, onDone = { focus.clearFocus() },
            )
            Spacer(Modifier.height(16.dp))
            Text(tr("연주하는 파트 (선택)", "Your instrument (optional)"), fontWeight = FontWeight.Bold)
            Text(
                tr("하나만 고를 수 있어요. 새 악보를 만들 때 미리 선택돼요.", "Pick one. It's preselected when you make a new score."),
                fontSize = 13.sp, color = cs.onSurface,
            )
            Spacer(Modifier.height(10.dp))
            // 한 사람은 파트 하나만 맡는다. 같은 칸을 다시 누르면 선택을 뺀다.
            PartChips(form.instruments) { inst ->
                edit { it.copy(instruments = if (inst in it.instruments) emptySet() else setOf(inst)) }
            }

            Spacer(Modifier.height(24.dp))
            SectionLabel(tr("약관 동의", "Agreements"))
            val all = form.over14 && form.agreeTerms && form.agreePrivacy
            AgreementRow(tr("전체 동의", "Agree to all"), all, bold = true, tag = "agree_all") { v ->
                edit { it.copy(over14 = v, agreeTerms = v, agreePrivacy = v) }
            }
            HorizontalDivider(Modifier.padding(vertical = 4.dp), color = cs.surfaceVariant)
            AgreementRow(tr("(필수) 만 14세 이상이에요", "(Required) I'm 14 or older"), form.over14, tag = "agree_age") { v ->
                edit { it.copy(over14 = v) }
            }
            AgreementRow(tr("(필수) 서비스 이용약관", "(Required) Terms of service"), form.agreeTerms, tag = "agree_terms", onView = { termsDialog = terms() }) { v ->
                edit { it.copy(agreeTerms = v) }
            }
            AgreementRow(tr("(필수) 개인정보 수집·이용", "(Required) Privacy policy"), form.agreePrivacy, tag = "agree_privacy", onView = { termsDialog = privacy() }) { v ->
                edit { it.copy(agreePrivacy = v) }
            }
            (agreementErr ?: failure)?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, color = cs.error, fontSize = 13.sp, modifier = Modifier.testTag("signup_error"))
            }
            Spacer(Modifier.height(16.dp))
        }
    }

    termsDialog?.let { (title, body) ->
        AlertDialog(
            onDismissRequest = { termsDialog = null },
            confirmButton = { TextButton(onClick = { termsDialog = null }) { Text(tr("닫기", "Close")) } },
            title = { Text(title) },
            text = { Text(body, fontSize = 14.sp, modifier = Modifier.verticalScroll(rememberScrollState())) },
        )
    }

    shownCode?.let { c ->
        AlertDialog(
            onDismissRequest = { shownCode = null },
            confirmButton = { TextButton(onClick = { shownCode = null }) { Text(tr("확인", "OK")) } },
            title = { Text(tr("인증번호를 보냈어요", "Code sent")) },
            text = {
                Column {
                    Text(tr("${SignUpValidator.normalizeEmail(form.email)}로 인증번호를 보냈어요.", "We sent a code to ${SignUpValidator.normalizeEmail(form.email)}."))
                    Spacer(Modifier.height(16.dp))
                    Text(tr("※ 시연 버전이라 메일 대신 여기에 보여드려요.", "※ Demo version: the code is shown here instead of by email."), fontSize = 12.sp, color = cs.onSurfaceVariant)
                    Text(
                        c, fontSize = 32.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace,
                        letterSpacing = 6.sp, color = cs.primary, textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    )
                }
            },
        )
    }
}

// ---------- 내 정보 (수정 · 화면 모드 · 로그아웃) ----------
@Composable
fun AccountScreen(
    user: User,
    auth: AuthRepository,
    photoVersion: Int,
    onBack: () -> Unit,
    onUpdated: (User) -> Unit,
    onLogout: () -> Unit,
) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    var confirm by remember { mutableStateOf(false) }
    var nickname by remember(user) { mutableStateOf(user.nickname) }
    var parts by remember(user) { mutableStateOf(user.instruments.toSet()) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val photo = remember(photoVersion, user.id) { ProfileStore.load(ctx, user.id) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) {
            if (ProfileStore.save(ctx, user.id, uri)) onUpdated(user)
            else Toast.makeText(ctx, tr("사진을 불러오지 못했어요", "Couldn't load the photo"), Toast.LENGTH_SHORT).show()
        }
    }
    val dirty = nickname.trim() != user.nickname || parts != user.instruments.toSet()
    val nicknameErr = error ?: SignUpValidator.nicknameError(nickname, typing = true)

    fun save() {
        if (busy) return
        focus.clearFocus()
        busy = true
        scope.launch {
            auth.updateProfile(user, nickname, parts)
                .onSuccess { onUpdated(it); Toast.makeText(ctx, tr("내 정보를 저장했어요", "Profile saved"), Toast.LENGTH_SHORT).show() }
                .onFailure { error = it.message }
            busy = false
        }
    }

    Page(tr("내 정보", "Profile"), onBack, bottom = {
        Button(
            onClick = { save() }, enabled = dirty && nicknameErr == null && !busy,
            modifier = Modifier.fillMaxWidth().height(52.dp).testTag("account_save"),
        ) { Text(if (dirty) tr("변경사항 저장", "Save changes") else tr("바뀐 내용이 없어요", "No changes")) }
    }) {
        Column(Modifier.weight(1f).imePadding().verticalScroll(rememberScrollState())) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Avatar(photo, nickname, 72.dp, Modifier.clickable {
                    picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                })
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text(user.nickname, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                    Text(user.email, color = cs.onSurfaceVariant, fontSize = 14.sp)
                    Row {
                        TextButton(onClick = {
                            picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                        }) { Text(tr("사진 바꾸기", "Change photo"), fontSize = 13.sp) }
                        if (photo != null) TextButton(onClick = { ProfileStore.remove(ctx, user.id); onUpdated(user) }) {
                            Text(tr("사진 삭제", "Remove photo"), fontSize = 13.sp, color = cs.onSurfaceVariant)
                        }
                    }
                }
            }

            Spacer(Modifier.height(20.dp))
            SectionLabel(tr("프로필 수정", "Edit profile"))
            AuthField(
                value = nickname, onValueChange = { nickname = it; error = null },
                label = tr("닉네임", "Nickname"), tag = "account_nickname", error = nicknameErr,
                hint = tr("${SignUpValidator.NICKNAME_MIN}~${SignUpValidator.NICKNAME_MAX}자, 한글·영문·숫자·_", "${SignUpValidator.NICKNAME_MIN}–${SignUpValidator.NICKNAME_MAX} characters: letters, numbers, _"),
                imeAction = ImeAction.Done, onDone = { focus.clearFocus() },
            )
            Spacer(Modifier.height(12.dp))
            Text(tr("연주하는 파트", "Your instrument"), fontWeight = FontWeight.Bold)
            Text(tr("하나만 고를 수 있어요. 새 악보를 만들 때 미리 선택돼요.", "Pick one. It's preselected when you make a new score."), fontSize = 13.sp, color = cs.onSurface)
            Spacer(Modifier.height(10.dp))
            PartChips(parts) { p -> parts = if (p in parts) emptySet() else setOf(p); error = null }

            Spacer(Modifier.height(24.dp))
            SectionLabel(tr("화면", "Display"))
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(cs.surface)
                    .clickable { AppSettings.setDark(ctx, !AppSettings.dark) }
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(tr("다크 모드", "Dark mode"), fontWeight = FontWeight.Bold)
                    Text(if (AppSettings.dark) tr("어두운 화면을 쓰고 있어요", "Using the dark look") else tr("밝은 화면을 쓰고 있어요", "Using the light look"),
                        fontSize = 12.sp, color = cs.onSurfaceVariant)
                }
                Switch(checked = AppSettings.dark, onCheckedChange = { AppSettings.setDark(ctx, it) },
                    modifier = Modifier.testTag("dark_mode"))
            }

            Spacer(Modifier.height(24.dp))
            SectionLabel(tr("언어", "Language"))
            LanguageSwitch(Modifier.fillMaxWidth(), fill = true)

            Spacer(Modifier.height(24.dp))
            SectionLabel(tr("계정", "Account"))
            InfoRow(tr("로그인 방법", "Sign-in method"), when (user.provider) {
                AuthProvider.EMAIL -> tr("이메일", "Email"); AuthProvider.GOOGLE -> "Google"; AuthProvider.APPLE -> "Apple"
            })
            InfoRow(tr("가입일", "Joined"), SimpleDateFormat("yyyy.MM.dd", Locale.KOREA).format(Date(user.createdAt)))
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = { confirm = true }, modifier = Modifier.testTag("logout")) {
                Text(tr("로그아웃", "Log out"), color = cs.error)
            }
            Spacer(Modifier.height(16.dp))
        }
    }
    if (confirm) {
        AlertDialog(
            onDismissRequest = { confirm = false },
            confirmButton = {
                TextButton(onClick = { confirm = false; onLogout() }, modifier = Modifier.testTag("logout_confirm")) {
                    Text(tr("로그아웃", "Log out"))
                }
            },
            dismissButton = { TextButton(onClick = { confirm = false }) { Text(tr("취소", "Cancel")) } },
            title = { Text(tr("로그아웃할까요?", "Log out?")) },
            text = {
                Text(tr("저장한 악보는 지워지지 않아요. 다시 로그인하면 볼 수 있어요.\n만들고 있던 악보는 멈춰요.",
                    "Saved scores stay. You'll see them when you log in again.\nScores in progress will stop."))
            },
        )
    }
}

// ---------- 언어 고르기 (한국어 / English) ----------
@Composable
fun LanguageSwitch(modifier: Modifier = Modifier, fill: Boolean = false) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    Row(modifier.clip(RoundedCornerShape(12.dp)).background(cs.surface).padding(3.dp)) {
        Lang.entries.forEach { l ->
            val on = AppSettings.lang == l
            Box(
                (if (fill) Modifier.weight(1f) else Modifier)
                    .clip(RoundedCornerShape(10.dp))
                    .background(if (on) cs.primary else cs.surface)
                    .clickable { AppSettings.setLang(ctx, l) }
                    .padding(horizontal = 14.dp, vertical = 8.dp)
                    .testTag("lang_${l.code}"),
                contentAlignment = Alignment.Center,
            ) {
                Text(l.label, fontSize = 13.sp, fontWeight = if (on) FontWeight.Bold else FontWeight.Normal,
                    color = if (on) cs.onPrimary else cs.onSurface)
            }
        }
    }
}

// ---------- 공통 입력 요소 ----------
@Composable
private fun SectionLabel(text: String) {
    Text(text, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
    Spacer(Modifier.height(8.dp))
}

@Composable
private fun AuthField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    tag: String,
    keyboardType: KeyboardType = KeyboardType.Text,
    error: String? = null,
    hint: String? = null,
    imeAction: ImeAction = ImeAction.Next,
    trailing: (@Composable () -> Unit)? = null,
    onNext: () -> Unit = {},
    onDone: () -> Unit = {},
) {
    OutlinedTextField(
        value = value, onValueChange = onValueChange, label = { Text(label) },
        singleLine = true, isError = error != null,
        supportingText = (error ?: hint)?.let { { Text(it) } },
        trailingIcon = trailing,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType, imeAction = imeAction),
        keyboardActions = KeyboardActions(onNext = { onNext() }, onDone = { onDone() }),
        modifier = Modifier.fillMaxWidth().testTag(tag),
    )
}

@Composable
private fun PasswordField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    tag: String,
    error: String? = null,
    hint: String? = null,
    imeAction: ImeAction = ImeAction.Next,
    onNext: () -> Unit = {},
    onDone: () -> Unit = {},
) {
    var visible by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value, onValueChange = onValueChange, label = { Text(label) },
        singleLine = true, isError = error != null,
        supportingText = (error ?: hint)?.let { { Text(it) } },
        visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
        trailingIcon = {
            TextButton(onClick = { visible = !visible }) { Text(if (visible) tr("숨기기", "Hide") else tr("보기", "Show"), fontSize = 12.sp) }
        },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = imeAction),
        keyboardActions = KeyboardActions(onNext = { onNext() }, onDone = { onDone() }),
        modifier = Modifier.fillMaxWidth().testTag(tag),
    )
}

/** 피아노·드럼·베이스·기타·보컬 중 여러 개 고르기. */
@Composable
private fun PartChips(selected: Set<String>, onToggle: (String) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Demo.PARTS.forEach { inst ->
            InstrumentChip(inst, inst in selected, Modifier.weight(1f)) { onToggle(inst) }
        }
    }
}

@Composable
private fun InstrumentChip(inst: String, on: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(14.dp)
    val fg = if (on) cs.onPrimary else cs.onSurface
    Column(
        modifier
            .clip(shape)
            .background(if (on) cs.primary else cs.surface)
            .border(BorderStroke(1.dp, if (on) cs.primary else cs.surfaceVariant), shape)
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp)
            .testTag("instrument_$inst"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // 고르면 그림도 글자와 같은 색으로 바뀐다.
        InstrumentIcon(inst, fg, size = 26.dp)
        Spacer(Modifier.height(2.dp))
        Text(Demo.kor(inst), fontSize = 12.sp, fontWeight = FontWeight.Bold, color = fg, maxLines = 1)
    }
}

@Composable
private fun AgreementRow(
    label: String,
    checked: Boolean,
    tag: String,
    bold: Boolean = false,
    onView: (() -> Unit)? = null,
    onChange: (Boolean) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().clickable { onChange(!checked) }.testTag(tag),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = onChange)
        Text(label, fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal, modifier = Modifier.weight(1f))
        if (onView != null) TextButton(onClick = onView) { Text(tr("보기", "View"), fontSize = 13.sp) }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    val cs = MaterialTheme.colorScheme
    Box(
        Modifier.fillMaxWidth().padding(vertical = 4.dp)
            .clip(RoundedCornerShape(14.dp)).background(cs.surface).padding(16.dp),
    ) {
        Column {
            Text(label, fontSize = 12.sp, color = cs.onSurfaceVariant)
            Spacer(Modifier.height(2.dp))
            Text(value, fontWeight = FontWeight.Bold)
        }
    }
}

// 시연용 요약문. 정식 약관은 서비스 공개 전에 따로 작성해야 한다.
private fun terms() = if (AppSettings.lang == Lang.EN) "Terms of service" to """
    1. ROCKY turns songs you upload into band scores (piano, drums, bass, guitar) and uses AI to write parts the song doesn't have.
    2. Upload only songs you have the right to use. Scores are for personal practice and non-commercial use.
    3. AI-made scores may differ from the original song, and ROCKY does not guarantee their accuracy.
    4. Using someone else's account or disrupting the service is not allowed.
""".trimIndent() else "서비스 이용약관" to """
    1. ROCKY는 사용자가 올린 음원을 밴드 악보(피아노·드럼·베이스·기타)로 바꾸고, 원곡에 없는 악기 파트를 AI로 만들어 줍니다.
    2. 사용자는 본인이 이용 권리를 가진 음원만 올려야 하며, 만든 악보는 개인 연습과 비상업적 목적으로만 쓸 수 있습니다.
    3. AI가 만든 채보·편곡 결과는 원곡과 다를 수 있으며, ROCKY는 결과의 정확성을 보증하지 않습니다.
    4. 다른 사람의 계정을 쓰거나 서비스를 방해하는 행위는 금지됩니다.
""".trimIndent()

private fun privacy() = if (AppSettings.lang == Lang.EN) "Privacy policy" to """
    • What we collect: email, password (stored encrypted so it can't be recovered), nickname, instrument (optional), profile photo (optional), time of agreement
    • Why: to identify you and log you in, keep your score library, and preset new scores
    • How long: until you delete your account
    • This version keeps your account only on this phone and sends it nowhere else.
    • You may refuse, but then you can't sign up.
""".trimIndent() else "개인정보 수집·이용" to """
    • 수집 항목: 이메일, 비밀번호(복원할 수 없는 형태로 암호화해 저장), 닉네임, 연주하는 파트(선택), 프로필 사진(선택), 약관 동의 시각
    • 이용 목적: 회원 식별과 로그인, 악보 보관함 제공, 악보 만들기 기본 설정
    • 보관 기간: 회원 탈퇴 시까지
    • 현재 버전은 회원 정보를 이 기기 안에만 저장하며 외부로 보내지 않습니다.
    • 동의를 거부할 수 있으나, 거부하면 가입할 수 없습니다.
""".trimIndent()
