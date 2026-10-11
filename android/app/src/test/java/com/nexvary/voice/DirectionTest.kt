package com.nexvary.voice
import org.junit.Assert.*
import org.junit.Test
class DirectionTest {
    @Test fun swappingRoundTrip() {
        val value = Direction("hi", "ar")
        assertEquals(Direction("ar", "hi"), value.swapped())
        assertEquals(value, value.swapped().swapped())
        assertTrue(value.isValid())
    }
    @Test fun sameLanguageBlocked() { assertFalse(Direction("en", "en").isValid()) }
    @Test fun languagesPresent() {
        assertTrue(Languages.choices.any { it.code == "ar" })
        assertTrue(Languages.choices.any { it.code == "hi" })
        assertTrue(Languages.choices.any { it.code == "ru" })
        assertTrue(Languages.choices.any { it.code == "bn" })
    }
}
