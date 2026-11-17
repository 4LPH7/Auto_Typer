package com.alph7.autotyper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SharedTextTest {
    @Test
    fun takesPlainTextFromAShareIntent() {
        assertEquals("hello", sharedTextFrom("android.intent.action.SEND", "text/plain", "hello"))
    }

    @Test
    fun ignoresOtherIntentsAndBlankText() {
        assertNull(sharedTextFrom("android.intent.action.VIEW", "text/plain", "hello"))
        assertNull(sharedTextFrom("android.intent.action.SEND", "image/png", "hello"))
        assertNull(sharedTextFrom("android.intent.action.SEND", "text/plain", "   "))
        assertNull(sharedTextFrom("android.intent.action.SEND", "text/plain", null))
    }
}
