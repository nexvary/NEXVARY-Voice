package com.nexvary.voice

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class VoiceResult(val translatedText: String, val source: String, val target: String)

object TranslationClient {
    private fun request(endpoint: String, path: String, token: String, payload: JSONObject?): JSONObject {
        val base = endpoint.trim().trimEnd('/')
        require(base.startsWith("https://") || base.startsWith("http://")) {
            "أدخل رابط خادم HTTP/HTTPS صالحًا"
        }
        val connection = ComputerPairing.connection(base + path)
        try {
            connection.requestMethod = if (payload == null) "GET" else "POST"
            connection.connectTimeout = 8000
            connection.readTimeout = 45000
            connection.setRequestProperty("Accept", "application/json")
            if (token.isNotBlank()) connection.setRequestProperty("Authorization", "Bearer " + token.trim())
            if (payload != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = connection.responseCode
            val body = if (code in 200..299) connection.inputStream.bufferedReader().use { it.readText() }
                else connection.errorStream?.bufferedReader()?.use { it.readText() } ?: "HTTP $code"
            if (code !in 200..299) throw IllegalStateException("HTTP $code: " + body.take(200))
            return JSONObject(body)
        } finally { connection.disconnect() }
    }

    fun health(endpoint: String, token: String): Boolean {
        val health = request(endpoint, "/health", token, null)
        if (health.optString("status") != "ok") return false
        if (health.optString("service") == "voice-gateway") {
            val capabilities = request(endpoint, "/v1/capabilities", token, null)
            return capabilities.optBoolean("worker_configured", false)
        }
        return true
    }

    fun translate(endpoint: String, token: String, text: String, direction: Direction): VoiceResult {
        require(direction.isValid()) { "اختر لغتين مختلفتين." }
        val response = request(endpoint, "/v1/translate", token, JSONObject()
            .put("text", text).put("source_language", direction.source)
            .put("target_language", direction.target))
        return VoiceResult(response.getString("translated_text"),
            response.getString("source_language"), response.getString("target_language"))
    }

    fun translateSrt(endpoint: String, token: String, content: String, direction: Direction): String {
        require(direction.isValid()) { "اختر لغتين مختلفتين." }
        require(content.isNotBlank() && content.length <= 500_000) { "ملف SRT فارغ أو أكبر من الحد المسموح." }
        return request(endpoint, "/v1/subtitles/translate", token, JSONObject()
            .put("srt", content).put("source_language", direction.source)
            .put("target_language", direction.target)).getString("srt")
    }
}
