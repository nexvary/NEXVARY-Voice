package com.nexvary.voice
import org.junit.Assert.*
import org.junit.Test

class PairingPayloadTest {
    private fun qr(endpoint:String="https://192.168.1.20:8443", fingerprint:String="a".repeat(64),code:String="b".repeat(43)) =
        "nexvary-voice://pair?endpoint="+java.net.URLEncoder.encode(endpoint,"UTF-8")+"&fingerprint="+fingerprint+"&code="+code
    @Test fun acceptsPrivateHttpsAndAllTrustFields() {
        val value=PairingPayload.parse(qr())
        assertEquals("https://192.168.1.20:8443",value.endpoint)
        assertEquals(64,value.fingerprint.length)
        assertEquals(43,value.code.length)
    }
    @Test fun rejectsPublicHttpCredentialsAndMissingPin() {
        for (url in listOf("http://192.168.1.20:8443","https://8.8.8.8:8443","https://user:pass@192.168.1.20:8443","https://192.168.1.20:8443/path","https://192.168.1.20:8443?token=x")) {
            try { PairingPayload.parse(qr(url));fail(url) } catch (_:IllegalArgumentException) {}
        }
        try { PairingPayload.parse(qr(fingerprint=""));fail() } catch (_:IllegalArgumentException) {}
    }
    @Test fun rejectsForeignQrAndOversizedInput() {
        for (input in listOf("https://example.org","x".repeat(3000))) {
            try { PairingPayload.parse(input);fail() } catch (_:IllegalArgumentException) {}
        }
    }
}
