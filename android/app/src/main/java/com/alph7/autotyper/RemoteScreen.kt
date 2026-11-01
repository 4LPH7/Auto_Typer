package com.alph7.autotyper

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle

private val CASES = listOf(
    "as_is" to "As is",
    "uppercase" to "UPPER",
    "lowercase" to "lower",
    "sentence_case" to "Sentence",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RemoteScreen(model: RemoteViewModel) {
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(model.pairing) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) { model.poll() }
    }
    val status = model.status
    val settings = model.settings

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Auto Typer",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = model::forget) { Text("Pair again") }
            }
            val problem = model.problem
            Text(
                problem ?: "Connected to ${model.pairing?.host}",
                style = MaterialTheme.typography.bodyMedium,
                color = if (problem != null) {
                    MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
            )

            OutlinedTextField(
                value = model.text,
                onValueChange = model::updateText,
                label = { Text("Text to type") },
                supportingText = { Text("{Enter}, {Tab} and {F1}–{F12} press keys") },
                minLines = 6,
                modifier = Modifier.fillMaxWidth(),
            )

            Text(
                "Settings",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                NumberField("Key delay", "ms", settings.speedMs, Modifier.weight(1f)) {
                    model.updateSettings(settings.copy(speedMs = it))
                }
                NumberField("Word pause", "ms", settings.delayMs, Modifier.weight(1f)) {
                    model.updateSettings(settings.copy(delayMs = it))
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                NumberField("Repeat (0 = ∞)", "×", settings.loopCount, Modifier.weight(1f)) {
                    model.updateSettings(settings.copy(loopCount = it))
                }
                NumberField("Jitter", "±%", settings.jitterPct, Modifier.weight(1f)) {
                    model.updateSettings(settings.copy(jitterPct = it))
                }
            }
            Text(
                "Letter case",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
                CASES.forEachIndexed { index, (value, label) ->
                    SegmentedButton(
                        selected = settings.capsMode == value,
                        onClick = { model.updateSettings(settings.copy(capsMode = value)) },
                        shape = SegmentedButtonDefaults.itemShape(index = index, count = CASES.size),
                    ) { Text(label) }
                }
            }

            StatusPanel(status)
            Controls(model, status)
        }
    }
}

@Composable
private fun StatusPanel(status: PcStatus?) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceContainer,
        shape = MaterialTheme.shapes.large,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                status?.title ?: "Connecting…",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            val detail = status?.detail.orEmpty()
            if (detail.isNotEmpty()) {
                Text(
                    detail,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            LinearProgressIndicator(
                progress = { status?.progress ?: 0f },
                color = MaterialTheme.colorScheme.tertiary,
                trackColor = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun Controls(model: RemoteViewModel, status: PcStatus?) {
    if (status != null && status.running) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(
                onClick = if (status.paused) model::resume else model::pause,
                modifier = Modifier.weight(1f).height(52.dp),
            ) { Text(if (status.paused) "Resume" else "Pause") }
            OutlinedButton(
                onClick = model::stop,
                modifier = Modifier.weight(1f).height(52.dp),
            ) { Text("Stop") }
        }
    } else {
        Button(
            onClick = model::start,
            enabled = status != null && model.text.isNotBlank(),
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) { Text("Start typing") }
        Text(
            "Your PC types into whichever window is active there, after a short countdown.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/** A whole-number field with its unit; keeps what the person typed while it's not a number. */
@Composable
private fun NumberField(
    label: String,
    unit: String,
    value: Int,
    modifier: Modifier,
    onChange: (Int) -> Unit,
) {
    var typed by remember(value) { mutableStateOf(value.toString()) }
    OutlinedTextField(
        value = typed,
        onValueChange = { input ->
            typed = input.filter(Char::isDigit).take(5)
            typed.toIntOrNull()?.let(onChange)
        },
        label = { Text(label, maxLines = 1) },
        suffix = { Text(unit) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = modifier,
    )
}
