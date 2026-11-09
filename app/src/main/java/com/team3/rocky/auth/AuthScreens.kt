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
import com.team3.rocky.Page
import com.team3.rocky.ProfileStore
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
    var editServer by remember { mutableStateOf(false) }

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
        Modifier.fillMaxSize().statusBarsPadding().imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
    ) {
        Spacer(Modifier.height(48.dp))
        Text("ROCKY", fontSize = 48.sp, fontWeight = FontWeight.Black, color = cs.primary)
        Text("어떤 곡이든, 우리 밴드 악보로", fontSize = 16.sp, color = cs.onSurfaceVariant)
        Spacer(Modifier.height(40.dp))

        AuthField(
            value = email, onValueChange = { email = it; error = null }, label = "이메일",
            keyboardType = KeyboardType.Email, tag = "login_email",
            onNext = { focus.moveFocus(FocusDirection.Down) },
        )
        Spacer(Modifier.height(12.dp))
        PasswordField(
            value = password, onValueChange = { password = it; error = null }, label = "비밀번호",
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
            else Text("로그인", fontSize = 17.sp)
        }
        Spacer(Modifier.height(12.dp))
        OutlinedButton(
            onClick = onSignUp, enabled = !busy,
            modifier = Modifier.fillMaxWidth().height(52.dp).testTag("go_signup"),
        ) { Text("이메일로 회원가입") }
        Spacer(Modifier.height(16.dp))
        Text(
            "Google · Apple 로그인은 준비 중이에요",
            fontSize = 12.sp, color = cs.onSurfaceVariant, modifier = Modifier.fillMaxWidth(),
        )
        // 회원 정보는 ROCKY 서버에 있으므로, 로그인 전에 서버 주소를 바꿀 수 있어야 한다.
        TextButton(onClick = { editServer = true }, modifier = Modifier.testTag("login_server")) {
            Text("서버 설정", fontSize = 12.sp)
        }
    }
    if (editServer) com.team3.rocky.ServerDialog(onDismiss = { editServer = false })
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
        ?: "이미 가입된 이메일이에요".takeIf { emailTaken }
    val passwordErr = SignUpValidator.passwordError(form.password)?.takeIf { show(form.password) }
    val confirmErr = SignUpValidator.passwordConfirmError(form.password, form.passwordConfirm)
        ?.takeIf { show(form.passwordConfirm) }
    val nicknameErr = serverErrors[SignUpValidator.Field.NICKNAME]
        ?: SignUpValidator.nicknameError(form.nickname, typing = !submitted)?.takeIf { show(form.nickname) }
        ?: "이미 사용 중인 닉네임이에요".takeIf { nicknameTaken }
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
        if (!verified) { codeError = "이메일 인증을 완료해 주세요"; return }
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

    Page("회원가입", onBack, dividers = true, bottom = {
        Button(
            onClick = { submit() }, enabled = !busy,
            modifier = Modifier.fillMaxWidth().height(56.dp).testTag("signup_submit"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = cs.onPrimary)
            else Text("가입하기", fontSize = 17.sp)
        }
    }) {
        Column(Modifier.fillMaxWidth().weight(1f).imePadding().verticalScroll(rememberScrollState())) {
            Spacer(Modifier.height(16.dp))
            Text("ROCKY와 함께\n밴드 악보를 만들어요", fontSize = 26.sp, fontWeight = FontWeight.Bold, lineHeight = 34.sp)
            Spacer(Modifier.height(24.dp))

            SectionLabel("계정")
            AuthField(
                value = form.email,
                onValueChange = { v -> edit { it.copy(email = v) }; codeError = null },
                label = "이메일", keyboardType = KeyboardType.Email, tag = "signup_email",
                error = emailErr,
                hint = when {
                    verified -> "✓ 인증 완료"
                    form.email.isNotEmpty() -> "✓ 사용할 수 있는 이메일이에요"
                    else -> "로그인할 때 아이디로 써요"
                },
                trailing = {
                    TextButton(
                        onClick = { sendCode() },
                        enabled = !verified && SignUpValidator.emailError(form.email) == null && !emailTaken,
                    ) { Text(if (verified) "인증됨" else if (codeSent) "다시 받기" else "인증번호 받기", fontSize = 12.sp) }
                },
                onNext = { focus.moveFocus(FocusDirection.Down) },
            )
            if (codeSent && !verified) {
                Spacer(Modifier.height(8.dp))
                AuthField(
                    value = code, onValueChange = { code = it.filter(Char::isDigit).take(EmailVerification.CODE_LENGTH); codeError = null },
                    label = "인증번호 ${EmailVerification.CODE_LENGTH}자리", keyboardType = KeyboardType.NumberPassword,
                    tag = "signup_code", error = codeError, hint = "메일로 받은 번호를 입력해 주세요 (5분 안에)",
                    trailing = { TextButton(onClick = { checkCode() }, enabled = code.length == EmailVerification.CODE_LENGTH) { Text("확인") } },
                    imeAction = ImeAction.Done, onDone = { checkCode() },
                )
            } else if (!codeSent && codeError != null) {
                Text(codeError!!, color = cs.error, fontSize = 12.sp, modifier = Modifier.padding(start = 16.dp))
            }
            Spacer(Modifier.height(8.dp))
            PasswordField(
                value = form.password, onValueChange = { v -> edit { it.copy(password = v) } },
                label = "비밀번호", tag = "signup_password", error = passwordErr,
                hint = if (form.password.isNotEmpty()) "✓ 사용할 수 있는 비밀번호예요"
                else "영문과 숫자를 포함해 ${SignUpValidator.PASSWORD_MIN}자 이상",
                onNext = { focus.moveFocus(FocusDirection.Down) },
            )
            Spacer(Modifier.height(8.dp))
            PasswordField(
                value = form.passwordConfirm,
                onValueChange = { v -> edit { it.copy(passwordConfirm = v) } },
                label = "비밀번호 확인", tag = "signup_password_confirm", error = confirmErr,
                hint = if (form.passwordConfirm.isNotEmpty()) "✓ 비밀번호가 일치해요" else null,
                onNext = { focus.moveFocus(FocusDirection.Down) },
            )

            Spacer(Modifier.height(20.dp))
            SectionLabel("프로필")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Avatar(photo, form.nickname, 64.dp, Modifier.clickable {
                    picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                })
                Spacer(Modifier.width(14.dp))
                Column {
                    Text("프로필 사진 (선택)", fontWeight = FontWeight.Bold)
                    Row {
                        TextButton(onClick = {
                            picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                        }) { Text(if (photo == null) "사진 고르기" else "다른 사진") }
                        if (photo != null) TextButton(onClick = { photo = null; photoUri = null }) {
                            Text("빼기", color = cs.onSurfaceVariant)
                        }
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
            AuthField(
                value = form.nickname, onValueChange = { v -> edit { it.copy(nickname = v) } },
                label = "닉네임", tag = "signup_nickname", error = nicknameErr,
                hint = if (form.nickname.isNotEmpty()) "✓ 사용할 수 있는 닉네임이에요"
                else "${SignUpValidator.NICKNAME_MIN}~${SignUpValidator.NICKNAME_MAX}자, 한글·영문·숫자·_",
                imeAction = ImeAction.Done, onDone = { focus.clearFocus() },
            )
            Spacer(Modifier.height(16.dp))
            Text("연주하는 파트 (선택)", fontWeight = FontWeight.Bold)
            Text(
                "하나만 고를 수 있어요. 새 악보를 만들 때 미리 선택돼요.",
                fontSize = 13.sp, color = cs.onSurface,
            )
            Spacer(Modifier.height(10.dp))
            // 한 사람은 파트 하나만 맡는다. 같은 칸을 다시 누르면 선택을 뺀다.
            PartChips(form.instruments) { inst ->
                edit { it.copy(instruments = if (inst in it.instruments) emptySet() else setOf(inst)) }
            }

            Spacer(Modifier.height(24.dp))
            SectionLabel("약관 동의")
            val all = form.over14 && form.agreeTerms && form.agreePrivacy
            AgreementRow("전체 동의", all, bold = true, tag = "agree_all") { v ->
                edit { it.copy(over14 = v, agreeTerms = v, agreePrivacy = v) }
            }
            HorizontalDivider(Modifier.padding(vertical = 4.dp), color = cs.surfaceVariant)
            AgreementRow("(필수) 만 14세 이상이에요", form.over14, tag = "agree_age") { v ->
                edit { it.copy(over14 = v) }
            }
            AgreementRow("(필수) 서비스 이용약관", form.agreeTerms, tag = "agree_terms", onView = { termsDialog = TERMS }) { v ->
                edit { it.copy(agreeTerms = v) }
            }
            AgreementRow("(필수) 개인정보 수집·이용", form.agreePrivacy, tag = "agree_privacy", onView = { termsDialog = PRIVACY }) { v ->
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
            confirmButton = { TextButton(onClick = { termsDialog = null }) { Text("닫기") } },
            title = { Text(title) },
            text = { Text(body, fontSize = 14.sp, modifier = Modifier.verticalScroll(rememberScrollState())) },
        )
    }

    shownCode?.let { c ->
        AlertDialog(
            onDismissRequest = { shownCode = null },
            confirmButton = { TextButton(onClick = { shownCode = null }) { Text("확인") } },
            title = { Text("인증번호를 보냈어요") },
            text = {
                Column {
                    Text("${SignUpValidator.normalizeEmail(form.email)}로 인증번호를 보냈어요.")
                    Spacer(Modifier.height(16.dp))
                    Text("※ 시연 버전이라 메일 대신 여기에 보여드려요.", fontSize = 12.sp, color = cs.onSurfaceVariant)
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
            else Toast.makeText(ctx, "사진을 불러오지 못했어요", Toast.LENGTH_SHORT).show()
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
                .onSuccess { onUpdated(it); Toast.makeText(ctx, "내 정보를 저장했어요", Toast.LENGTH_SHORT).show() }
                .onFailure { error = it.message }
            busy = false
        }
    }

    Page("내 정보", onBack, bottom = {
        Button(
            onClick = { save() }, enabled = dirty && nicknameErr == null && !busy,
            modifier = Modifier.fillMaxWidth().height(52.dp).testTag("account_save"),
        ) { Text(if (dirty) "변경사항 저장" else "바뀐 내용이 없어요") }
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
                        }) { Text("사진 바꾸기", fontSize = 13.sp) }
                        if (photo != null) TextButton(onClick = { ProfileStore.remove(ctx, user.id); onUpdated(user) }) {
                            Text("사진 삭제", fontSize = 13.sp, color = cs.onSurfaceVariant)
                        }
                    }
                }
            }

            Spacer(Modifier.height(20.dp))
            SectionLabel("프로필 수정")
            AuthField(
                value = nickname, onValueChange = { nickname = it; error = null },
                label = "닉네임", tag = "account_nickname", error = nicknameErr,
                hint = "${SignUpValidator.NICKNAME_MIN}~${SignUpValidator.NICKNAME_MAX}자, 한글·영문·숫자·_",
                imeAction = ImeAction.Done, onDone = { focus.clearFocus() },
            )
            Spacer(Modifier.height(12.dp))
            Text("연주하는 파트", fontWeight = FontWeight.Bold)
            Text("하나만 고를 수 있어요. 새 악보를 만들 때 미리 선택돼요.", fontSize = 13.sp, color = cs.onSurface)
            Spacer(Modifier.height(10.dp))
            PartChips(parts) { p -> parts = if (p in parts) emptySet() else setOf(p); error = null }

            Spacer(Modifier.height(24.dp))
            SectionLabel("화면")
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(cs.surface)
                    .clickable { AppSettings.setDark(ctx, !AppSettings.dark) }
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("다크 모드", fontWeight = FontWeight.Bold)
                    Text(if (AppSettings.dark) "어두운 화면을 쓰고 있어요" else "밝은 화면을 쓰고 있어요",
                        fontSize = 12.sp, color = cs.onSurfaceVariant)
                }
                Switch(checked = AppSettings.dark, onCheckedChange = { AppSettings.setDark(ctx, it) },
                    modifier = Modifier.testTag("dark_mode"))
            }

            Spacer(Modifier.height(24.dp))
            SectionLabel("계정")
            InfoRow("로그인 방법", when (user.provider) {
                AuthProvider.EMAIL -> "이메일"; AuthProvider.GOOGLE -> "Google"; AuthProvider.APPLE -> "Apple"
            })
            InfoRow("가입일", SimpleDateFormat("yyyy.MM.dd", Locale.KOREA).format(Date(user.createdAt)))
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = { confirm = true }, modifier = Modifier.testTag("logout")) {
                Text("로그아웃", color = cs.error)
            }
            Spacer(Modifier.height(16.dp))
        }
    }
    if (confirm) {
        AlertDialog(
            onDismissRequest = { confirm = false },
            confirmButton = {
                TextButton(onClick = { confirm = false; onLogout() }, modifier = Modifier.testTag("logout_confirm")) {
                    Text("로그아웃")
                }
            },
            dismissButton = { TextButton(onClick = { confirm = false }) { Text("취소") } },
            title = { Text("로그아웃할까요?") },
            text = { Text("저장한 악보는 지워지지 않아요. 다시 로그인하면 볼 수 있어요.\n만들고 있던 악보는 취소돼요.") },
        )
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
            TextButton(onClick = { visible = !visible }) { Text(if (visible) "숨기기" else "보기", fontSize = 12.sp) }
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
        if (onView != null) TextButton(onClick = onView) { Text("보기", fontSize = 13.sp) }
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
private val TERMS = "서비스 이용약관" to """
    1. ROCKY는 사용자가 올린 음원을 밴드 악보(피아노·드럼·베이스·기타)로 바꾸고, 원곡에 없는 악기 파트를 AI로 만들어 줍니다.
    2. 사용자는 본인이 이용 권리를 가진 음원만 올려야 하며, 만든 악보는 개인 연습과 비상업적 목적으로만 쓸 수 있습니다.
    3. AI가 만든 채보·편곡 결과는 원곡과 다를 수 있으며, ROCKY는 결과의 정확성을 보증하지 않습니다.
    4. 다른 사람의 계정을 쓰거나 서비스를 방해하는 행위는 금지됩니다.
""".trimIndent()

private val PRIVACY = "개인정보 수집·이용" to """
    • 수집 항목: 이메일, 비밀번호(복원할 수 없는 형태로 암호화해 저장), 닉네임, 연주하는 파트(선택), 프로필 사진(선택), 약관 동의 시각
    • 이용 목적: 회원 식별과 로그인, 악보 보관함 제공, 악보 만들기 기본 설정
    • 보관 기간: 회원 탈퇴 시까지
    • 현재 버전은 회원 정보를 이 기기 안에만 저장하며 외부로 보내지 않습니다.
    • 동의를 거부할 수 있으나, 거부하면 가입할 수 없습니다.
""".trimIndent()
