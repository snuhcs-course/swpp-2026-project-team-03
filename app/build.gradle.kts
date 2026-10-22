plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    jacoco                                     // [테스트] 커버리지 측정
}

android {
    namespace = "com.team3.rocky"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.team3.rocky"
        minSdk = 34
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
        // [테스트] debug 빌드로 테스트할 때 커버리지를 기록
        debug {
            enableUnitTestCoverage = true      // unit test 커버리지
            enableAndroidTestCoverage = true   // UI test 커버리지
        }
    }
    // [테스트] Robolectric이 안드로이드 리소스를 쓸 수 있게
    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
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
    testImplementation("org.robolectric:robolectric:4.16.1")          // [테스트] JVM에서 안드로이드 흉내
    testImplementation("androidx.test:core-ktx:1.7.0")                 // [테스트] ApplicationProvider
    androidTestImplementation("androidx.test.espresso:espresso-intents:3.7.0")  // [테스트] 공유 Intent 확인
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}

// ============================================================
// [테스트] JaCoCo 커버리지 리포트
//   ./gradlew testDebugUnitTest jacocoTestReport
//   → app/build/reports/jacoco/jacocoTestReport/html/index.html
//   UI 테스트(connectedDebugAndroidTest)를 먼저 돌렸다면 그 결과도 합쳐서 보여줘요.
// ============================================================
jacoco { toolVersion = "0.8.14" }

tasks.withType<Test>().configureEach {
    configure<JacocoTaskExtension> {
        isIncludeNoLocationClasses = true      // Robolectric 테스트도 커버리지에 포함
        excludes = listOf("jdk.internal.*")
    }
}

// 커버리지에서 제외: 자동 생성 코드, 테마(색상만 있음), 앱 진입점, Compose 내부 생성 클래스
val coverageExcludes = listOf(
    "**/R.class", "**/R\$*.class", "**/BuildConfig.*", "**/Manifest*.*",
    "**/*Test*.*", "**/ThemeKt*.*", "**/ui/theme/**", "**/MainActivity*.*", "**/ComposableSingletons*.*",
)

tasks.register<JacocoReport>("jacocoTestReport") {
    group = "verification"
    description = "Unit test (+ UI test, if run) coverage report"
    dependsOn("testDebugUnitTest")

    val build = layout.buildDirectory.get().asFile
    reports {
        html.required.set(true)
        xml.required.set(true)
    }
    classDirectories.setFrom(
        fileTree("$build/intermediates/built_in_kotlinc/debug/compileDebugKotlin/classes") { exclude(coverageExcludes) },
        fileTree("$build/tmp/kotlin-classes/debug") { exclude(coverageExcludes) },
    )
    sourceDirectories.setFrom(files("src/main/java", "src/main/kotlin"))
    executionData.setFrom(
        fileTree(build) {
            include(
                "outputs/unit_test_code_coverage/debugUnitTest/*.exec",
                "outputs/code_coverage/debugAndroidTest/connected/**/*.ec",
            )
        }
    )
}
