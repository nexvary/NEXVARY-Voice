"""Argos-backed text translation without silent demo/fallback translations."""
from __future__ import annotations

from typing import Protocol


class TranslationUnavailable(RuntimeError):
    """No usable translation model is available for this language pair."""


class Translator(Protocol):
    def translate(self, text: str, source: str, target: str) -> str: ...


class ArgosTranslator:
    def translate(self, text: str, source: str, target: str) -> str:
        if source == target:
            return text
        try:
            import argostranslate.translate as argos
        except ImportError as exc:
            raise TranslationUnavailable(
                "Argos Translate is not installed. Install the offline extra and language models."
            ) from exc

        languages = {language.code: language for language in argos.get_installed_languages()}
        from_language = languages.get(source)
        to_language = languages.get(target)
        if from_language is None or to_language is None:
            raise TranslationUnavailable(f"Install language packages for {source} to {target}.")

        try:
            translation = from_language.get_translation(to_language)
            if translation is None:
                raise TranslationUnavailable(f"No installed translation path from {source} to {target}.")
            result = translation.translate(text)
        except TranslationUnavailable:
            raise
        except Exception as exc:
            raise TranslationUnavailable(
                f"Cannot translate {source} to {target} using installed models."
            ) from exc
        if not result or not result.strip():
            raise TranslationUnavailable("The translation engine returned an empty result.")
        return result
