package com.nexvary.voice

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.AudioAttributes
import android.media.MediaRecorder
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Foreground-only, one-direction speech turns, 3.2-second microphone chunks. */
class LiveStreamController(private val context: Context) {
    var active by mutableStateOf(false)
        private set
    var state by mutableStateOf("متوقف")
        private set
    var original by mutableStateOf("")
        private set
    var translated by mutableStateOf("")
        private set

    private val running = AtomicBoolean(false)
    private val playing = AtomicBoolean(false)
    private var socket: WebSocket? = null
    private var capture: AudioRecord? = null
    private var speaker: AudioTrack? = null
    private var thread: Thread? = null
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    fun start(url: String, token: String, source: String, target: String) {
        if (running.get()) return
        if (source == target) { state = "اختر لغتين مختلفتين."; return }
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) !=
            PackageManager.PERMISSION_GRANTED) {
            state = "يلزم إذن الميكروفون."
            return
        }
        val raw = url.trim().trimEnd('/')
        val destination = when {
            raw.startsWith("https://") -> "wss://" + raw.removePrefix("https://")
            raw.startsWith("http://") && BuildConfig.DEBUG -> "ws://" + raw.removePrefix("http://")
            else -> { state = "يلزم خادم HTTPS، باستثناء التجارب على نسخة Debug."; return }
        } + "/v1/live/audio"

        val minIn = AudioRecord.getMinBufferSize(16000,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val minOut = AudioTrack.getMinBufferSize(16000,
            AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (minIn <= 0 || minOut <= 0) { state = "الجهاز لا يدعم صوت PCM16 المطلوب."; return }
        try {
            capture = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,
                16000, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, maxOf(4096, minIn * 2))
            if (capture?.state != AudioRecord.STATE_INITIALIZED) {
                state = "تعذر تهيئة الميكروفون."; stop(); return
            }
            speaker = AudioTrack.Builder()
                .setAudioAttributes(AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setAudioFormat(AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(16000).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setTransferMode(AudioTrack.MODE_STREAM)
                .setBufferSizeInBytes(maxOf(minOut * 2, 4096))
                .build()
            speaker?.play()
        } catch (error: Exception) {
            state = "تعذر تهيئة الصوت: " + (error.message ?: "خطأ")
            stop()
            return
        }
        val request = Request.Builder().url(destination).apply {
            if (token.isNotBlank()) addHeader("Authorization", "Bearer " + token.trim())
        }.build()
        running.set(true)
        active = true
        state = "جارٍ الاتصال بالمترجم الصوتي…"
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                val hello = JSONObject()
                    .put("source_language", source).put("target_language", target)
                    .put("format", "pcm_s16le").put("sample_rate", 16000)
                webSocket.send(hello.toString())
                state = "المترجم يستمع؛ تُعالج الجمل في مقاطع كل 3.2 ثوانٍ."
                startCapture()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val data = JSONObject(text)
                    if (data.optString("type") == "translated") {
                        original = data.optString("original_text")
                        translated = data.optString("translated_text")
                        state = "وصلت الترجمة الصوتية."
                    } else if (data.optString("type") == "error") {
                        state = "عطل في الترجمة: " + data.optString("message")
                    }
                } catch (_: Exception) { state = "رد غير مفهوم من الخادم." }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                // Mute mic forwarding during playback to prevent translated-audio feedback.
                playing.set(true)
                try {
                    val samples = bytes.toByteArray()
                    speaker?.write(samples, 0, samples.size, AudioTrack.WRITE_BLOCKING)
                } finally {
                    playing.set(false)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                state = "انقطع اتصال البث: " + (t.message ?: "اتصال غير متاح")
                stop()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                stop()
            }
        })
    }

    private fun startCapture() {
        thread = Thread {
            try {
                val recorder = capture ?: return@Thread
                recorder.startRecording()
                val pcm = ByteArray(3200) // 100 ms at 16 kHz x 16 bit.
                while (running.get()) {
                    val count = recorder.read(pcm, 0, pcm.size, AudioRecord.READ_BLOCKING)
                    if (count > 0 && !playing.get()) {
                        socket?.send(ByteString.of(*pcm.copyOf(count)))
                    }
                }
            } catch (error: Exception) {
                if (running.get()) state = "تعذر استمرار التقاط الصوت."
            }
        }.also { it.name = "NEXVARY-Voice-Microphone"; it.start() }
    }

    fun stop() {
        running.set(false)
        active = false
        val oldSocket = socket
        socket = null
        try { oldSocket?.close(1000, "Stopped") } catch (_: Exception) { }
        try { capture?.stop() } catch (_: Exception) { }
        try { capture?.release() } catch (_: Exception) { }
        capture = null
        try { speaker?.pause(); speaker?.flush(); speaker?.release() } catch (_: Exception) { }
        speaker = null
        thread?.interrupt()
        thread = null
        if (!state.startsWith("انقطع") && !state.startsWith("عطل")) state = "تم إيقاف الاستماع."
    }

    fun stateMessage(text: String) { state = text }

    fun release() {
        stop()
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
    }
}
