import java.util.Properties

// 서버 주소와 키: local.properties(커밋하지 않음) 또는 Gradle 속성(-Procky.serverUrl=...)으로 넣는다.
// 없으면 주소는 http://localhost:8000 (폰을 USB로 노트북에 연결하고 adb reverse tcp:8000 tcp:8000),
// 키는 비워 둔다. 앱의 '서버 설정'에서도 바꿀 수 있다.
val localProps = Properties().apply {
    rootProject.file("local.properties").takeIf { it.isFile }?.inputStream()?.use { load(it) }
}
fun rockyProp(name: String, default: String): String =
    ((findProperty(name) as String?) ?: localProps.getProperty(name))?.takeIf { it.isNotBlank() } ?: default

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.team3.rocky"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.team3.rocky"
        // 팀 시연 갤럭시가 안드로이드 13(API 33)이라 낮춤. NewApi 검사는 lint가 CI에서 막는다.
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        buildConfigField("String", "ROCKY_SERVER_URL", "\"${rockyProp("rocky.serverUrl", "http://localhost:8000")}\"")
        buildConfigField("String", "ROCKY_API_KEY", "\"${rockyProp("rocky.apiKey", "")}\"")
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    lint {
        // 최소 버전(26)보다 새 안드로이드에만 있는 기능을 쓰면 빌드를 멈춘다.
        checkOnly += "NewApi"
        abortOnError = true
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    testImplementation(libs.junit)
    // 안드로이드의 org.json은 로컬 단위 테스트에서 비어 있어서, 테스트에서는 원본 라이브러리를 쓴다.
    testImplementation(libs.orgjson)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}