package com.nexvary.voice

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat

class MainActivity : ComponentActivity() {
    private lateinit var audio: VoiceAudioController
    private var pendingLanguage = "ar-EG"
    private val permission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) audio.listen(pendingLanguage)
        else audio.message = "يلزم إذن الميكروفون أو يمكنك كتابة النص يدويًا."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        audio = VoiceAudioController(this)
        setContent {
            VoiceApp(audio) { language ->
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
                    PackageManager.PERMISSION_GRANTED
                ) audio.listen(language)
                else {
                    pendingLanguage = language
                    permission.launch(Manifest.permission.RECORD_AUDIO)
                }
            }
        }
    }

    override fun onDestroy() {
        audio.release()
        super.onDestroy()
    }
}
