package com.alph7.autotyper

import android.app.Application
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.IOException
import java.util.UUID

/** Holds the pairing, polls the PC while the remote screen is visible, and sends commands. */
class RemoteViewModel(application: Application) : AndroidViewModel(application) {
    private val prefs = application.getSharedPreferences("pairing", Context.MODE_PRIVATE)
    private var client: PcClient? = null
    private var settingsLoaded = false // take the PC's settings once per pairing
    private var pendingStartId: String? = null // reused if a start has to be retried
    private val wakeUp = Channel<Unit>(Channel.CONFLATED) // a Wi-Fi change polls at once
    private val connectivity = application.getSystemService(ConnectivityManager::class.java)
    private val wifiCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            wakeUp.trySend(Unit)
        }
    }

    var pairing by mutableStateOf<Pairing?>(null)
        private set
    var status by mutableStateOf<PcStatus?>(null)
        private set
    var problem by mutableStateOf<String?>(null)
        private set
    var text by mutableStateOf("")
        private set
    var settings by mutableStateOf(TypingSettings())
        private set
    var changingPc by mutableStateOf(false) // true while the connect screen is open again
        private set

    init {
        val host = prefs.getString("host", null)
        val code = prefs.getString("code", null)
        if (host != null && code != null) {
            usePairing(Pairing(host, prefs.getInt("port", Pairing.DEFAULT_PORT), code))
        }
        connectivity.registerNetworkCallback(
            NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build(),
            wifiCallback,
        )
    }

    fun pair(newPairing: Pairing) {
        prefs.edit()
            .putString("host", newPairing.host)
            .putInt("port", newPairing.port)
            .putString("code", newPairing.code)
            .apply()
        changingPc = false
        usePairing(newPairing)
    }

    fun startChangingPc() {
        changingPc = true
    }

    fun cancelChangingPc() {
        changingPc = false
    }

    fun updateText(value: String) {
        text = value.take(MAX_TEXT_LENGTH)
        pendingStartId = null
    }

    fun updateSettings(value: TypingSettings) {
        settings = value
        pendingStartId = null
    }

    /** Polls until cancelled: fast while typing, slower when idle or unreachable. */
    suspend fun poll() {
        while (true) {
            val current = client ?: return
            val wait = try {
                val latest = withContext(Dispatchers.IO) { current.status() }
                status = latest
                problem = null
                if (!settingsLoaded) {
                    settings = latest.settings
                    settingsLoaded = true
                }
                if (latest.running) 250L else 1_000L
            } catch (e: PcException) {
                problem = e.message
                2_000L
            } catch (e: IOException) {
                problem = UNREACHABLE
                2_000L
            }
            withTimeoutOrNull(wait) { wakeUp.receive() }
        }
    }

    fun start() {
        val id = pendingStartId ?: UUID.randomUUID().toString().also { pendingStartId = it }
        send(onAnswered = { pendingStartId = null }) { it.start(id, text, settings) }
    }

    fun pause() = send { it.pause() }

    fun resume() = send { it.resume() }

    fun stop() = send { it.stop() }

    override fun onCleared() {
        connectivity.unregisterNetworkCallback(wifiCallback)
    }

    private fun usePairing(newPairing: Pairing) {
        pairing = newPairing
        client = PcClient(newPairing)
        status = null
        problem = null
        settingsLoaded = false
    }

    private fun send(onAnswered: () -> Unit = {}, action: (PcClient) -> Unit) {
        val current = client ?: return
        viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) { action(current) }
                onAnswered()
                problem = null
                status = withContext(Dispatchers.IO) { current.status() }
            } catch (e: PcException) {
                onAnswered()
                problem = e.message
            } catch (e: IOException) {
                // It may not have arrived; a retried start reuses its id, so it types once.
                problem = UNREACHABLE
            }
        }
    }

    companion object {
        const val MAX_TEXT_LENGTH = 60_000 // keeps requests under the PC's 256 KB limit
        private const val UNREACHABLE =
            "Can't reach your PC. Check that its phone remote is on and you're on the same Wi-Fi."
    }
}
