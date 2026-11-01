package com.alph7.autotyper

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PcClientTest {
    @Test
    fun readsTheDesktopQrCode() {
        val pairing = Pairing.fromQr("autotyper://pair?host=192.168.1.5&port=8765&code=K7Q2M9XD&v=1")
        assertEquals(Pairing("192.168.1.5", 8765, "K7Q2M9XD"), pairing)
    }

    @Test
    fun ignoresOtherQrCodes() {
        assertNull(Pairing.fromQr("https://example.com/pair?host=1.2.3.4&port=1&code=K7Q2M9XD"))
        assertNull(Pairing.fromQr("autotyper://pair?host=192.168.1.5&port=8765&code=SHORT"))
    }

    @Test
    fun readsATypedAddressAndCode() {
        assertEquals(
            Pairing("192.168.1.5", 8765, "K7Q2M9XD"),
            Pairing.fromTyped(" 192.168.1.5:8765 ", "k7q2 m9xd"),
        )
        assertEquals(Pairing.DEFAULT_PORT, Pairing.fromTyped("192.168.1.5", "K7Q2M9XD")?.port)
        assertNull(Pairing.fromTyped("192.168.1.5:99999", "K7Q2M9XD"))
    }

    @Test
    fun readsTheStatusReply() {
        val status = PcStatus.fromJson(
            JSONObject(
                """{"version":1,"phase":"typing","title":"Typing","detail":"58 of 149 keystrokes",
                "done":58,"total":149,"elapsed_s":2.4,"settings":{"speed_ms":40,"delay_ms":0,
                "loop_count":2,"human_jitter_pct":10,"caps_mode":"uppercase"}}""",
            ),
        )
        assertTrue(status.running)
        assertEquals(58f / 149, status.progress, 0.0001f)
        assertEquals(TypingSettings(40, 0, 2, 10, "uppercase"), status.settings)
    }

    @Test
    fun sendsSettingsUnderTheProtocolNames() {
        val json = TypingSettings(speedMs = 30, jitterPct = 5, capsMode = "lowercase").toJson()
        assertEquals(30, json.getInt("speed_ms"))
        assertEquals(5, json.getInt("human_jitter_pct"))
        assertEquals("lowercase", json.getString("caps_mode"))
    }
}
