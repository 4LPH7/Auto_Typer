package com.alph7.autotyper

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Text shared from another app; only on the first start, not after a rotation.
        val shared = if (savedInstanceState == null) {
            sharedTextFrom(intent?.action, intent?.type, intent?.getStringExtra(Intent.EXTRA_TEXT))
        } else {
            null
        }
        setContent {
            AutoTyperTheme {
                val model: RemoteViewModel = viewModel()
                LaunchedEffect(shared) { shared?.let(model::updateText) }
                val choosingPc = model.pairing == null || model.changingPc
                // Back from "Change PC" returns to the remote instead of closing the app.
                BackHandler(enabled = model.changingPc && model.pairing != null) {
                    model.cancelChangingPc()
                }
                if (choosingPc) {
                    ConnectScreen(
                        onPaired = model::pair,
                        onBack = if (model.pairing != null) model::cancelChangingPc else null,
                    )
                } else {
                    RemoteScreen(model)
                }
            }
        }
    }
}

/** The text another app shared with "Send to Auto Typer", or null for anything else. */
fun sharedTextFrom(action: String?, type: String?, text: String?): String? =
    text?.takeIf { action == Intent.ACTION_SEND && type == "text/plain" && it.isNotBlank() }
