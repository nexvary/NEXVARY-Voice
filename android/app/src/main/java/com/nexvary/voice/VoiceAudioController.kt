package com.nexvary.voice

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.util.Locale

class VoiceAudioController(private val activity: Activity) {
    var message by mutableStateOf("جاهز للاستماع")
    var recognized by mutableStateOf("")
        private set
    var captureId by mutableIntStateOf(0)
        private set
    var listening by mutableStateOf(false)
        private set
    private var recognizer: SpeechRecognizer? = null
    private var ttsReady = false
    private val tts = TextToSpeech(activity) { code ->
        ttsReady = code == TextToSpeech.SUCCESS
        if (!ttsReady) message = "محرك النطق غير متاح على الجهاز."
    }

    fun listen(language: String) {
        if (!SpeechRecognizer.isRecognitionAvailable(activity)) {
            message = "التعرف الصوتي غير متاح على الجهاز. أدخل النص يدويًا."
            return
        }
        stop()
        recognizer = SpeechRecognizer.createSpeechRecognizer(activity)
        recognizer?.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) { listening = true; message = "تحدث الآن…" }
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() { listening = false; message = "تحويل الكلام إلى نص…" }
            override fun onError(error: Int) { listening = false; message = "تعذر التعرف على الصوت (رمز $error)." }
            override fun onResults(results: Bundle?) {
                listening = false
                val words = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                if (words.isNullOrBlank()) {
                    message = "لم يُلتقط كلام واضح."
                } else {
                    recognized = words
                    captureId++
                    message = "تم التقاط الكلام. يمكنك تعديل النص قبل الترجمة."
                }
            }
            override fun onPartialResults(partialResults: Bundle?) {
                // Partial recognition remains local; the user reviews the final text.
            }
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, language)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
        }
        recognizer?.startListening(intent)
    }

    fun stop() {
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
        listening = false
    }

    fun speak(text: String, code: String) {
        if (!ttsReady) { message = "الترجمة جاهزة، لكن نطق الجهاز غير متاح."; return }
        val voice = Languages.choices.firstOrNull { it.code == code } ?: return
        val locale = Locale.forLanguageTag(voice.tag)
        if (tts.isLanguageAvailable(locale) < TextToSpeech.LANG_AVAILABLE) {
            message = "صوت اللغة " + voice.title + " غير مثبت على الجهاز."
            return
        }
        tts.language = locale
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "nexvary-voice")
    }

    fun release() {
        stop()
        tts.stop()
        tts.shutdown()
    }
}
