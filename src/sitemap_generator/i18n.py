"""i18n — Einfache Internationalisierung ueber JSON-Sprachdateien."""

from __future__ import annotations

import json
import logging
from importlib import resources

logger = logging.getLogger(__name__)

_strings: dict[str, str] = {}
_current_lang: str = "de"

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"


def load_locale(lang: str) -> None:
    """Laedt eine Sprachdatei (z.B. 'de', 'en')."""
    global _strings, _current_lang

    if lang not in SUPPORTED_LANGUAGES:
        logger.warning("Sprache '%s' nicht unterstuetzt, verwende '%s'", lang, DEFAULT_LANGUAGE)
        lang = DEFAULT_LANGUAGE

    try:
        locale_files = resources.files("sitemap_generator") / "locale" / f"{lang}.json"
        raw = locale_files.read_text(encoding="utf-8")
        _strings = json.loads(raw)
        _current_lang = lang
    except Exception:
        logger.exception("Fehler beim Laden der Sprachdatei '%s'", lang)
        _strings = {}
        _current_lang = lang


def current_language() -> str:
    """Gibt die aktuell geladene Sprache zurueck."""
    return _current_lang


def t(key: str, **kwargs: object) -> str:
    """Uebersetzt einen Schluessel. Platzhalter via {name} und kwargs."""
    template = _strings.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
