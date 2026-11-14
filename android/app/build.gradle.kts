plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Firebase / Google sign-in is switched on automatically when google-services.json is present.
if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}

// Server address, first match wins:
//   1. android/api.properties   (written by termux-build.sh, survives re-extracting the project)
//   2. -PAPI_BASE_URL=...  or  API_BASE_URL in gradle.properties
//   3. API_BASE_URL environment variable
// The address must end with /api/v1/
val apiProps = java.util.Properties().apply {
    val f = rootProject.file("api.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
val apiBaseUrl: String = apiProps.getProperty("API_BASE_URL")
    ?: (project.findProperty("API_BASE_URL") as String?)
    ?: System.getenv("API_BASE_URL")
    ?: "https://aussnsc-api.onrender.com/api/v1/"

android {
    namespace = "com.aussnsc.app"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.aussnsc.app"
        minSdk = 23
        targetSdk = 35
        versionCode = 3
        versionName = "2.1.0"
        buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
    }
    // One fixed key for every build, so the SHA-1 you register in Firebase never changes.
    signingConfigs {
        getByName("debug") {
            storeFile = file("debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }
    buildTypes {
        release {
            // Not debuggable => Compose runs much faster than in a debug build. Signed with the fixed key above.
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    lint {
        checkReleaseBuilds = false   // keeps the CI build quick and avoids lint-only failures
        abortOnError = false
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}
dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.core:core-ktx:1.15.0")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:okhttp-tls:4.12.0")   // trust extra roots on Android 7
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.8.1")

    // Google sign-in through Firebase
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-auth")
    implementation("androidx.credentials:credentials:1.3.0")
    implementation("androidx.credentials:credentials-play-services-auth:1.3.0")
    implementation("com.google.android.libraries.identity.googleid:googleid:1.1.1")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
