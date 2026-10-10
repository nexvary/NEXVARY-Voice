package com.nexvary.voice
data class Direction(val source: String, val target: String) {
    init { require(source.isNotBlank() && target.isNotBlank()) }
    fun swapped() = Direction(target, source)
    fun isValid() = source != target
}
data class VoiceLanguage(val code: String, val tag: String, val title: String)
object Languages {
    val choices = listOf(
        VoiceLanguage("hi", "hi-IN", "الهندية 🇮🇳"),
        VoiceLanguage("ar", "ar-EG", "العربية 🇪🇬"),
        VoiceLanguage("en", "en-US", "الإنجليزية 🇺🇸"),
        VoiceLanguage("tr", "tr-TR", "التركية 🇹🇷"),
        VoiceLanguage("fr", "fr-FR", "الفرنسية 🇫🇷"),
        VoiceLanguage("de", "de-DE", "الألمانية 🇩🇪"),
        VoiceLanguage("es", "es-ES", "الإسبانية 🇪🇸"),
        VoiceLanguage("it", "it-IT", "الإيطالية 🇮🇹")
    )
}
