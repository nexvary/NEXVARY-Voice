package com.nexvary.voice
data class Direction(val source: String, val target: String) {
    init { require(source.isNotBlank() && target.isNotBlank()) }
    fun swapped() = Direction(target, source)
    fun isValid() = source != target
}
data class VoiceLanguage(val code: String, val tag: String, val title: String)
object Languages {
    val choices = listOf(
        VoiceLanguage("hi", "hi-IN", "हिन्दी"),
        VoiceLanguage("ar", "ar-EG", "العربية"),
        VoiceLanguage("en", "en-US", "English"),
        VoiceLanguage("tr", "tr-TR", "Türkçe"),
        VoiceLanguage("fr", "fr-FR", "Français"),
        VoiceLanguage("de", "de-DE", "Deutsch"),
        VoiceLanguage("es", "es-ES", "Español"),
        VoiceLanguage("it", "it-IT", "Italiano"),
        VoiceLanguage("ru", "ru-RU", "Русский"),
        VoiceLanguage("bn", "bn-BD", "বাংলা")
    )
}
