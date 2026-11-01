package com.alph7.autotyper

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AutoTyperTheme {
                val model: RemoteViewModel = viewModel()
                if (model.pairing == null) {
                    ConnectScreen(onPaired = model::pair)
                } else {
                    RemoteScreen(model)
                }
            }
        }
    }
}
