package com.nexvary.voice

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import okhttp3.OkHttpClient
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.net.URLDecoder
import java.security.KeyStore
import java.security.MessageDigest
import java.security.cert.X509Certificate
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/** QR supplies a physical trust anchor. Never accept a changed certificate. */
data class PairingPayload(val endpoint: String, val fingerprint: String, val code: String) {
    companion object {
        fun parse(raw: String): PairingPayload {
            require(raw.length <= 2048) { "رمز الاقتران غير صالح" }
            val uri = URI(raw)
            require(uri.scheme == "nexvary-voice" && uri.host == "pair") { "هذا ليس رمز NEXVARY" }
            val values = uri.rawQuery.orEmpty().split('&').associate {
                val parts=it.split('=',limit=2)
                require(parts.size==2)
                URLDecoder.decode(parts[0],"UTF-8") to URLDecoder.decode(parts[1],"UTF-8")
            }
            val endpoint=values["endpoint"] ?: error("رمز ناقص")
            val server=URI(endpoint)
            require(server.scheme=="https" && server.rawUserInfo==null && server.rawQuery==null &&
                server.rawFragment==null && server.path.orEmpty().isEmpty() && server.port in 1..65535)
            val octets=server.host.orEmpty().split('.').map { it.toIntOrNull() ?: -1 }
            require(octets.size==4 && octets.all { it in 0..255 } &&
                (octets[0]==10 || octets[0]==192 && octets[1]==168 || octets[0]==172 && octets[1] in 16..31)) {
                "الاقتران متاح على شبكة خاصة فقط"
            }
            val fingerprint=values["fingerprint"].orEmpty()
            val code=values["code"].orEmpty()
            require(Regex("[a-f0-9]{64}").matches(fingerprint) && Regex("[A-Za-z0-9_-]{40,64}").matches(code))
            return PairingPayload(endpoint,fingerprint,code)
        }
    }
}

object ComputerPairing {
    data class Session(val endpoint:String,val fingerprint:String,val token:String,val expires:Long)
    var active:Session?=null
        private set
    private const val ALIAS="nexvary-computer-pairing"
    private fun trust(fingerprint:String):X509TrustManager = object:X509TrustManager {
        override fun getAcceptedIssuers():Array<X509Certificate> = emptyArray()
        override fun checkClientTrusted(chain:Array<X509Certificate>,authType:String) { throw java.security.cert.CertificateException("Unsupported") }
        override fun checkServerTrusted(chain:Array<X509Certificate>,authType:String) {
            if(chain.isEmpty()) throw java.security.cert.CertificateException("Missing certificate")
            chain[0].checkValidity()
            val actual=MessageDigest.getInstance("SHA-256").digest(chain[0].encoded).joinToString("") { "%02x".format(it) }
            if(!MessageDigest.isEqual(actual.toByteArray(),fingerprint.toByteArray()))
                throw java.security.cert.CertificateException("شهادة الكمبيوتر تغيرت؛ أعد مسح QR")
        }
    }
    private fun tls(manager:X509TrustManager)=SSLContext.getInstance("TLS").apply { init(null,arrayOf(manager),null) }
    fun connection(url:String):HttpURLConnection {
        val conn=URL(url).openConnection() as HttpURLConnection
        conn.instanceFollowRedirects=false
        active?.takeIf { System.currentTimeMillis()<it.expires && url.startsWith(it.endpoint+"/") }?.let {
            require(conn is HttpsURLConnection)
            conn.sslSocketFactory=tls(trust(it.fingerprint)).socketFactory
        }
        return conn
    }
    fun client(endpoint:String):OkHttpClient.Builder {
        val builder=OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        active?.takeIf { it.endpoint==endpoint.trimEnd('/') && System.currentTimeMillis()<it.expires }?.let {
            val manager=trust(it.fingerprint)
            builder.sslSocketFactory(tls(manager).socketFactory,manager)
        }
        return builder
    }
    private fun key():SecretKey {
        val store=KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(ALIAS,null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    private fun save(context:Context,session:Session) {
        val plain=JSONObject().put("endpoint",session.endpoint).put("fingerprint",session.fingerprint)
            .put("token",session.token).put("expires",session.expires).toString().toByteArray(Charsets.UTF_8)
        val cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key())
        val blob=Base64.encodeToString(cipher.iv+cipher.doFinal(plain),Base64.NO_WRAP)
        context.getSharedPreferences("paired_computer",Context.MODE_PRIVATE).edit().putString("encrypted",blob).apply()
    }
    fun restore(context:Context):Session? {
        try {
            val blob=context.getSharedPreferences("paired_computer",Context.MODE_PRIVATE).getString("encrypted",null) ?: return null
            val bytes=Base64.decode(blob,Base64.NO_WRAP);require(bytes.size>28)
            val cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,bytes.copyOfRange(0,12)))
            val data=JSONObject(String(cipher.doFinal(bytes.copyOfRange(12,bytes.size)),Charsets.UTF_8))
            val session=Session(data.getString("endpoint"),data.getString("fingerprint"),data.getString("token"),data.getLong("expires"))
            if(session.expires<=System.currentTimeMillis()) { forget(context);return null }
            active=session;return session
        } catch(_:Exception) { forget(context);return null }
    }
    fun forget(context:Context) {
        active=null
        context.getSharedPreferences("paired_computer",Context.MODE_PRIVATE).edit().clear().apply()
    }
    fun pair(context:Context,payload:PairingPayload):Session {
        val manager=trust(payload.fingerprint)
        val conn=URL(payload.endpoint+"/pair").openConnection() as HttpsURLConnection
        conn.instanceFollowRedirects=false;conn.sslSocketFactory=tls(manager).socketFactory
        conn.requestMethod="POST";conn.connectTimeout=8000;conn.readTimeout=15000;conn.doOutput=true
        conn.setRequestProperty("Content-Type","application/json")
        try {
            conn.outputStream.use { it.write(JSONObject().put("code",payload.code).toString().toByteArray(Charsets.UTF_8)) }
            require(conn.responseCode==200) { "انتهت صلاحية الرمز أو تعذر الاتصال. اعرض QR جديدًا وتأكد من نفس Wi-Fi." }
            val body=conn.inputStream.bufferedReader().use { it.readText() };require(body.length<=1024)
            val response=JSONObject(body);val token=response.getString("token")
            require(Regex("[A-Za-z0-9_-]{40,64}").matches(token))
            val session=Session(payload.endpoint,payload.fingerprint,token,System.currentTimeMillis()+response.getLong("expires_in")*1000)
            save(context,session);active=session;return session
        } finally { conn.disconnect() }
    }
}
