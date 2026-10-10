package com.nexvary.voice

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import java.util.Locale

/** Turn-taking MVP, not a simultaneous conversation or broadcast audio capture. */
class MainActivity : Activity() {
    private val navy = Color.rgb(11, 20, 38)
    private val gold = Color.rgb(234, 192, 112)
    private val teal = Color.rgb(83, 225, 197)
    private lateinit var source: Spinner
    private lateinit var target: Spinner
    private lateinit var textInput: EditText
    private lateinit var serverInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var status: TextView
    private lateinit var result: TextView
    private lateinit var translate: Button
    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var previous: VoiceResult? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = navy
        window.navigationBarColor = navy
        createUi()
        tts = TextToSpeech(this) { code ->
            ttsReady = code == TextToSpeech.SUCCESS
            if (!ttsReady) message("محرك النطق غير متاح، لكن الترجمة النصية متاحة.")
        }
    }

    private fun caption(value: String, size: Float = 16f, color: Int = Color.WHITE): TextView =
        TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            setPadding(6, 14, 6, 14)
        }

    private fun edit(hintText: String, password: Boolean = false) = EditText(this).apply {
        hint = hintText
        setTextColor(Color.WHITE)
        setHintTextColor(Color.LTGRAY)
        setBackgroundColor(Color.rgb(24, 38, 61))
        setPadding(18, 16, 18, 16)
        if (password) {
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
    }

    private fun button(title: String, click: () -> Unit) = Button(this).apply {
        text = title
        isAllCaps = false
        textSize = 16f
        setTextColor(navy)
        setBackgroundColor(gold)
        setOnClickListener { click() }
    }

    private fun chooser(): Spinner = Spinner(this).apply {
        val adapter = ArrayAdapter(
            this@MainActivity, android.R.layout.simple_spinner_item, Languages.choices.map { it.title }
        )
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        this.adapter = adapter
        setBackgroundColor(Color.WHITE)
    }

    private fun createUi() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(22, 24, 22, 24)
            layoutDirection = View.LAYOUT_DIRECTION_RTL
        }
        val scroll = ScrollView(this).apply {
            setBackgroundColor(navy)
            layoutDirection = View.LAYOUT_DIRECTION_RTL
            addView(layout)
        }
        layout.addView(caption("NEXVARY VOICE", 26f, gold))
        layout.addView(caption("ترجمة المحادثات الثنائية • نسخة اختبارية", 16f, teal))
        layout.addView(caption("كل شخص يتحدث بدوره؛ بعد سماع الترجمة استخدم زر تبديل الاتجاه.", 14f))
        layout.addView(caption("لغة المتحدث", 16f, gold))
        source = chooser()
        layout.addView(source)
        layout.addView(caption("لغة المستمع", 16f, gold))
        target = chooser()
        target.setSelection(1)
        layout.addView(target)
        layout.addView(button("↔ تبديل الاتجاه") {
            val index = source.selectedItemPosition
            source.setSelection(target.selectedItemPosition)
            target.setSelection(index)
            message("تغيّر اتجاه الترجمة.")
        })
        layout.addView(caption("الكلام الأصلي", 16f, gold))
        textInput = edit("تحدث عبر الميكروفون أو اكتب نصًا").apply { minLines = 3 }
        layout.addView(textInput)
        layout.addView(button("🎙 استمع للمتحدث") { listen() })
        translate = button("ترجم وانطق الصوت") { translateTurn() }
        layout.addView(translate)
        layout.addView(caption("النتيجة", 16f, gold))
        result = caption("ستظهر الترجمة هنا.", 19f).apply {
            setBackgroundColor(Color.rgb(24, 38, 61))
            minHeight = 130
        }
        layout.addView(result)
        layout.addView(button("🔊 إعادة نطق الترجمة") { previous?.let { speak(it) } })
        layout.addView(caption("اتصال الخادم", 18f, teal))
        layout.addView(caption("10.0.2.2 للمحاكي فقط؛ الهاتف الحقيقي يحتاج خادمًا متاحًا له.", 13f))
        serverInput = edit("رابط الخادم").apply {
            setText("http://10.0.2.2:8000")
            setSingleLine(true)
            textDirection = View.TEXT_DIRECTION_LTR
        }
        layout.addView(serverInput)
        tokenInput = edit("API Token (اختياري للتجربة المحلية)", password = true)
        layout.addView(tokenInput)
        status = caption("جاهز. تحقق من تثبيت نماذج اللغات بالخادم.", 14f, teal)
        layout.addView(status)
        layout.addView(caption("توجيه الصوت لسماعات Bluetooth تتحكم به إعدادات Android.", 13f))
        setContentView(scroll)
    }

    private fun message(value: String) { status.text = value }

    private fun selectedDirection() = Direction(
        Languages.choices[source.selectedItemPosition].code,
        Languages.choices[target.selectedItemPosition].code
    )

    private fun translateTurn() {
        val utterance = textInput.text.toString().trim()
        if (utterance.isEmpty()) { message("أدخل نصًا أو سجل صوتًا أولًا."); return }
        val direction = selectedDirection()
        if (!direction.isValid()) { message("اختر لغتين مختلفتين."); return }
        translate.isEnabled = false
        message("جارٍ الاتصال بخادم الترجمة...")
        val url = serverInput.text.toString()
        val token = tokenInput.text.toString()
        Thread {
            try {
                val translated = TranslationClient.translate(url, token, utterance, direction)
                runOnUiThread {
                    previous = translated
                    result.text = translated.translatedText
                    translate.isEnabled = true
                    message("تمت الترجمة. بدّل الاتجاه للرد.")
                    speak(translated)
                }
            } catch (exc: Exception) {
                runOnUiThread {
                    translate.isEnabled = true
                    message("تعذر إتمام الترجمة: " + (exc.message ?: "خطأ غير محدد"))
                }
            }
        }.start()
    }

    private fun speak(voice: VoiceResult) {
        val speaker = tts
        if (!ttsReady || speaker == null) { message("الترجمة مكتوبة، ولكن محرك نطق الجهاز غير متاح."); return }
        val language = Languages.choices.firstOrNull { it.code == voice.target } ?: return
        val locale = Locale.forLanguageTag(language.tag)
        if (speaker.isLanguageAvailable(locale) < TextToSpeech.LANG_AVAILABLE) {
            message("يلزم تثبيت صوت لغة " + language.title + " على الجهاز.")
            return
        }
        speaker.language = locale
        speaker.speak(voice.translatedText, TextToSpeech.QUEUE_FLUSH, null, "voice-turn")
    }

    private fun listen() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 42)
            return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            message("خدمة التعرف على الكلام غير متاحة. يمكنك الكتابة.")
            return
        }
        recognizer?.destroy()
        recognizer = SpeechRecognizer.createSpeechRecognizer(this)
        recognizer?.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) { message("تحدث الآن...") }
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() { message("جارٍ فهم الكلام...") }
            override fun onError(error: Int) { message("تعذر التقاط الصوت ($error). استخدم الكتابة.") }
            override fun onResults(results: Bundle?) {
                val words = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                if (words.isNullOrBlank()) { message("لم يتم التقاط كلام واضح."); return }
                textInput.setText(words)
                translateTurn()
            }
            override fun onPartialResults(partialResults: Bundle?) {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        val code = Languages.choices[source.selectedItemPosition].tag
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, code)
        }
        recognizer?.startListening(intent)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 42) {
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) listen()
            else message("صلاحية الميكروفون غير متاحة؛ استخدم الكتابة.")
        }
    }

    override fun onDestroy() {
        recognizer?.destroy()
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }
}
