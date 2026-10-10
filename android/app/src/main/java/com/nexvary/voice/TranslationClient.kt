package com.nexvary.voice
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
data class VoiceResult(val translatedText: String, val source: String, val target: String)
object TranslationClient {
    fun translate(endpoint: String, token: String, text: String, direction: Direction): VoiceResult {
        require(direction.isValid()) { "اختر لغتين مختلفتين" }
        val base = endpoint.trim().trimEnd('/')
        require(base.startsWith("https://") || base.startsWith("http://")) { "أدخل رابط HTTP/HTTPS صحيحًا" }
        val request = JSONObject()
            .put("text", text)
            .put("source_language", direction.source)
            .put("target_language", direction.target)
        val connection = URL("$base/v1/translate").openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 10000
            connection.readTimeout = 30000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            if (token.isNotBlank()) connection.setRequestProperty("Authorization", "Bearer " + token.trim())
            connection.outputStream.use { it.write(request.toString().toByteArray(Charsets.UTF_8)) }
            val status = connection.responseCode
            val response = if (status in 200..299) {
                connection.inputStream.bufferedReader().use { it.readText() }
            } else connection.errorStream?.bufferedReader()?.use { it.readText() } ?: "HTTP $status"
            if (status !in 200..299) throw IllegalStateException("HTTP $status: " + response.take(240))
            val body = JSONObject(response)
            return VoiceResult(body.getString("translated_text"),
                body.getString("source_language"), body.getString("target_language"))
        } finally { connection.disconnect() }
    }
}
