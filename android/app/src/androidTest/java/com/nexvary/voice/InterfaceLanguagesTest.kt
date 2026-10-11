package com.nexvary.voice
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import android.graphics.Bitmap
import java.io.File
import org.junit.Rule
import org.junit.Test

/** Emulator UI proof only: does not claim physical microphone/camera testing. */
class InterfaceLanguagesTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    @Test fun fiveLanguagesAndPairingButton() {
        rule.onNodeWithText("الإعدادات").performClick()
        var selected="العربية"
        val choices=listOf("ar" to "العربية","en" to "English","fr" to "Français","de" to "Deutsch","ru" to "Русский")
        for ((code,name) in choices) {
            if(name!=selected) {
                rule.onNodeWithText(selected,useUnmergedTree=true).performScrollTo().performClick()
                rule.onNodeWithText(name,useUnmergedTree=true).performClick()
                selected=name
            }
            rule.waitForIdle()
            val config=android.content.res.Configuration(rule.activity.resources.configuration)
            config.setLocale(java.util.Locale.forLanguageTag(code))
            val context=rule.activity.createConfigurationContext(config)
            val qr=UiStrings.render("مسح QR لربط الكمبيوتر",context)
            rule.onNodeWithText(qr).performScrollTo().assertIsDisplayed().assertHasClickAction()
            rule.waitForIdle()
            val instrumentation=InstrumentationRegistry.getInstrumentation()
            val directory=File(rule.activity.getExternalFilesDir(null),"screenshots").apply { mkdirs() }
            val bitmap=instrumentation.uiAutomation.takeScreenshot()
            requireNotNull(bitmap)
            val file=File(directory,"android-settings-$code.png")
            file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
            // Test-only shell identity exports proof before Gradle uninstalls the app.
            val command="mkdir -p /sdcard/Download/nexvary-screenshots && cp ${file.absolutePath} /sdcard/Download/nexvary-screenshots/"
            android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(command)).use { it.readBytes() }
        }
    }
}
