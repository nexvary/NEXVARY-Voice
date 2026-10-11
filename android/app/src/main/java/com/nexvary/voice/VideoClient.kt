package com.nexvary.voice

import android.content.Context
import android.net.Uri
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/** Streams bounded MP4 upload/download without buffering entire videos in Android memory. */
object VideoClient {
    private fun connection(url: String, token: String): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15000
        conn.readTimeout = 120000
        if (token.isNotBlank())
            conn.setRequestProperty("Authorization", "Bearer " + token.trim())
        return conn
    }

    private fun read(conn: HttpURLConnection): JSONObject {
        val code = conn.responseCode
        val text = if (code in 200..299)
            conn.inputStream.bufferedReader().use { it.readText() }
        else conn.errorStream?.bufferedReader()?.use { it.readText() } ?: "HTTP " + code
        if (code !in 200..299) throw IllegalStateException("HTTP " + code + ": " + text.take(180))
        return JSONObject(text)
    }

    fun submit(context: Context, endpoint: String, token: String,
               uri: Uri, pair: Direction): String {
        require(pair.isValid()) { "اختر لغتين مختلفتين" }
        val boundary = "nexvary" + UUID.randomUUID().toString().replace("-", "")
        val conn = connection(endpoint.trimEnd('/') + "/v1/dub/jobs", token)
        try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setChunkedStreamingMode(65536)
            conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary)
            conn.outputStream.use { sink ->
                fun text(value: String) { sink.write(value.toByteArray(Charsets.UTF_8)) }
                fun field(name: String, value: String) {
                    text("--" + boundary + "\r\n")
                    text("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n")
                    text(value + "\r\n")
                }
                field("source_language", pair.source)
                field("target_language", pair.target)
                text("--" + boundary + "\r\n")
                text("Content-Disposition: form-data; name=\"file\"; filename=\"video.mp4\"\r\n")
                text("Content-Type: video/mp4\r\n\r\n")
                val stream = context.contentResolver.openInputStream(uri)
                    ?: throw IllegalArgumentException("تعذر فتح ملف الفيديو")
                stream.use { input ->
                    val bytes = ByteArray(65536)
                    var total = 0L
                    while (true) {
                        val count = input.read(bytes)
                        if (count < 0) break
                        total += count
                        require(total <= 80L * 1024L * 1024L) {
                            "الحجم الأقصى للفيديو 80 ميجابايت"
                        }
                        sink.write(bytes, 0, count)
                    }
                }
                text("\r\n--" + boundary + "--\r\n")
            }
            return read(conn).getString("job_id")
        } finally { conn.disconnect() }
    }

    fun status(endpoint: String, token: String, id: String): JSONObject {
        require(Regex("[a-f0-9-]{36}").matches(id)) { "معرف المهمة غير صالح" }
        val conn = connection(endpoint.trimEnd('/') + "/v1/dub/jobs/" + id, token)
        try { return read(conn) } finally { conn.disconnect() }
    }

    fun download(context: Context, endpoint: String, token: String,
                 id: String, target: Uri) {
        require(Regex("[a-f0-9-]{36}").matches(id)) { "معرف المهمة غير صالح" }
        val conn = connection(endpoint.trimEnd('/') + "/v1/dub/jobs/" + id + "/video", token)
        try {
            if (conn.responseCode != 200) throw IllegalStateException("الملف لم يجهز بعد")
            val sink = context.contentResolver.openOutputStream(target)
                ?: throw IllegalStateException("لا يمكن الكتابة في المكان المحدد")
            sink.use { out -> conn.inputStream.use { it.copyTo(out, 65536) } }
        } finally { conn.disconnect() }
    }
}
