package com.alph7.autotyper

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// The desktop app's palette: neutral surfaces stepped by lightness, the primary
// action shown by inversion, and one lime hue (tertiary) only on live progress.
private val DarkColors = darkColorScheme(
    primary = Color(0xFFFFFFFF),
    onPrimary = Color(0xFF000000),
    background = Color(0xFF0C0D0F),
    onBackground = Color(0xFFFFFFFF),
    surface = Color(0xFF0C0D0F),
    onSurface = Color(0xFFFFFFFF),
    surfaceContainer = Color(0xFF15171A),
    surfaceVariant = Color(0xFF24272B),
    onSurfaceVariant = Color(0xFFB4B4B4),
    secondaryContainer = Color(0xFF3D4148),
    onSecondaryContainer = Color(0xFFFFFFFF),
    outline = Color(0xFF444444),
    outlineVariant = Color(0xFF24272B),
    tertiary = Color(0xFFC6F24E),
    error = Color(0xFFE5566F),
)

private val LightColors = lightColorScheme(
    primary = Color(0xFF1D1F20),
    onPrimary = Color(0xFFFFFFFF),
    background = Color(0xFFF9FAFB),
    onBackground = Color(0xFF111111),
    surface = Color(0xFFF9FAFB),
    onSurface = Color(0xFF111111),
    surfaceContainer = Color(0xFFFFFFFF),
    surfaceVariant = Color(0xFFEEF0F2),
    onSurfaceVariant = Color(0xFF5F6368),
    secondaryContainer = Color(0xFFFFFFFF),
    onSecondaryContainer = Color(0xFF111111),
    outline = Color(0xFFD1D5DB),
    outlineVariant = Color(0xFFEEF0F2),
    tertiary = Color(0xFF4D7C0F),
    error = Color(0xFFC4242A),
)

@Composable
fun AutoTyperTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (isSystemInDarkTheme()) DarkColors else LightColors,
        content = content,
    )
}
