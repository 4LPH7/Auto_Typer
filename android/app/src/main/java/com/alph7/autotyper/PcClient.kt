package com.alph7.autotyper

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI

/** Where the PC is, and the code that lets this phone control it. */
data class Pairing(val host: String, val port: Int, val code: String) {
    companion object {
        const val DEFAULT_PORT = 8765

        /** Reads the desktop's QR code: `autotyper://pair?host=…&port=…&code=…&v=1`. */
        fun fromQr(text: String): Pairing? {
            val uri = runCatching { URI(text.trim()) }.getOrNull() ?: return null
            if (uri.scheme != "autotyper" || uri.host != "pair") return null
            val params = uri.rawQuery.orEmpty().split("&").mapNotNull { pair ->
                val parts = pair.split("=", limit = 2)
                if (parts.size == 2) parts[0] to parts[1] else null
            }.toMap()
            return of(params["host"], params["port"], params["code"])
        }

        /** Reads what a person types: `192.168.1.5:8765` (port optional) and `K7Q2 M9XD`. */
        fun fromTyped(address: String, code: String): Pairing? {
            val trimmed = address.trim()
            return if (":" in trimmed) {
                of(trimmed.substringBeforeLast(":"), trimmed.substringAfterLast(":"), code)
            } else {
                of(trimmed, DEFAULT_PORT.toString(), code)
            }
        }

        private fun of(host: String?, port: String?, code: String?): Pairing? {
            val portNumber = port?.toIntOrNull()?.takeIf { it in 1..65535 } ?: return null
            val cleanCode = code.orEmpty().filter { it.isLetterOrDigit() }.uppercase()
            if (host.isNullOrBlank() || cleanCode.length != 8) return null
            return Pairing(host.trim(), portNumber, cleanCode)
        }
    }
}

/** The typing options, named as in the PC's protocol (docs/remote-protocol.md). */
data class TypingSettings(
    val speedMs: Int = 25,
    val delayMs: Int = 0,
    val loopCount: Int = 1,
    val jitterPct: Int = 0,
    val capsMode: String = "as_is",
) {
    fun toJson(): JSONObject = JSONObject()
        .put("speed_ms", speedMs)
        .put("delay_ms", delayMs)
        .put("loop_count", loopCount)
        .put("human_jitter_pct", jitterPct)
        .put("caps_mode", capsMode)

    companion object {
        fun fromJson(json: JSONObject) = TypingSettings(
            speedMs = json.optInt("speed_ms", 25),
            delayMs = json.optInt("delay_ms", 0),
            loopCount = json.optInt("loop_count", 1),
            jitterPct = json.optInt("human_jitter_pct", 0),
            capsMode = json.optString("caps_mode", "as_is"),
        )
    }
}

/** What the PC is doing, as `GET /api/status` reports it. */
data class PcStatus(
    val phase: String,
    val title: String,
    val detail: String,
    val done: Int,
    val total: Int,
    val settings: TypingSettings,
) {
    val running: Boolean get() = phase in RUNNING_PHASES
    val paused: Boolean get() = phase == "paused"
    val progress: Float get() = if (total > 0) done.toFloat() / total else 0f

    companion object {
        private val RUNNING_PHASES = setOf("countdown", "typing", "paused")

        fun fromJson(json: JSONObject) = PcStatus(
            phase = json.optString("phase"),
            title = json.optString("title"),
            detail = json.optString("detail"),
            done = json.optInt("done"),
            total = json.optInt("total"),
            settings = TypingSettings.fromJson(json.optJSONObject("settings") ?: JSONObject()),
        )
    }
}

/** The PC answered but refused, e.g. a wrong code or typing already running. */
class PcException(message: String) : Exception(message)

/** Talks to the PC app over HTTP. Calls block; run them off the main thread. */
class PcClient(private val pairing: Pairing) {
    private val base = "http://${pairing.host}:${pairing.port}/api"

    fun status(): PcStatus = PcStatus.fromJson(request("GET", "/status"))

    fun start(requestId: String, text: String, settings: TypingSettings) {
        val body = JSONObject()
            .put("request_id", requestId)
            .put("text", text)
            .put("settings", settings.toJson())
        request("POST", "/start", body)
    }

    fun pause() {
        request("POST", "/pause")
    }

    fun resume() {
        request("POST", "/resume")
    }

    fun stop() {
        request("POST", "/stop")
    }

    private fun request(method: String, path: String, body: JSONObject? = null): JSONObject {
        val connection = URI(base + path).toURL().openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 3_000
            connection.readTimeout = 8_000
            connection.setRequestProperty("Authorization", "Bearer ${pairing.code}")
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val reply = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            val json = runCatching { JSONObject(reply) }.getOrDefault(JSONObject())
            if (status !in 200..299) {
                throw PcException(json.optString("error").ifEmpty { "The PC answered $status." })
            }
            return json
        } finally {
            connection.disconnect()
        }
    }
}
