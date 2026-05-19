"""Persistente Einstellungen fuer den Sitemap Generator."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

# Einstellungsdatei im User-Verzeichnis
_SETTINGS_DIR = Path.home() / ".sitemap-generator"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"


# textual-themes 0.5 hat 25 Themes umbenannt (trademark-safety pass).
# Settings-Files aelterer Versionen koennen alte Slugs gespeichert
# haben — die werden beim Laden transparent gemappt.
_LEGACY_THEME_MAP: dict[str, str] = {
    "c64": "brotkasten",
    "amiga": "boing",
    "atari-st": "gemstone",
    "ibm-terminal": "classic-terminal",
    "nextstep": "next",
    "beos": "bebox",
    "ubuntu": "bunty",
    "macos": "cupertino",
    "windows-xp": "luna",
    "msdos": "commandr",
    "solaris-cde": "motif",
    "os2-warp": "warp",
    "opensuse": "geeko",
    "linux-mint": "minty",
    "red-hat": "crimson",
    "raspberry-pi": "razzy",
    "freebsd": "beastie",
    "tudor": "fifty-eight",
    "goldfinger": "goldfinder",
    "hulk": "hulkula",
    "batman": "flughund",
    "gameboy": "brick",
    "pan-am": "clipper",
    "miami-vice": "miami",
    "martini-racing": "racing",
    "superman": "metropolis",
    "spiderman": "spiderized",
    "gulf-racing": "textual-dark",  # entferntes Theme -> Textual Default
}


class Settings:
    """Persistente Einstellungen (Theme etc.)."""

    def __init__(self) -> None:
        self.theme: str = "textual-dark"
        self.respect_robots: bool = True
        self.render: bool = False
        self.language: str = "de"
        self.concurrency: int = 8
        self.timeout: int = 30
        self.max_depth: int = 10
        self.show_preview: bool = False

    def save(self) -> None:
        """Speichert die Einstellungen in eine JSON-Datei."""
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "theme": self.theme,
            "respect_robots": self.respect_robots,
            "render": self.render,
            "language": self.language,
            "concurrency": self.concurrency,
            "timeout": self.timeout,
            "max_depth": self.max_depth,
            "show_preview": self.show_preview,
        }
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> Settings:
        """Laedt die Einstellungen oder gibt Defaults zurueck.

        Migriert dabei alte Theme-Slugs aus textual-themes < 0.5 auf
        ihre aktuellen Namen und persistiert die Migration.

        Returns:
            Settings-Instanz.
        """
        settings = cls()
        if _SETTINGS_FILE.is_file():
            try:
                data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
                settings.theme = data.get("theme", settings.theme)
                settings.respect_robots = data.get("respect_robots", settings.respect_robots)
                settings.render = data.get("render", settings.render)
                settings.language = data.get("language", settings.language)
                settings.concurrency = int(data.get("concurrency", settings.concurrency))
                settings.timeout = int(data.get("timeout", settings.timeout))
                settings.max_depth = int(data.get("max_depth", settings.max_depth))
                settings.show_preview = bool(data.get("show_preview", settings.show_preview))
            except Exception:
                pass

        # Legacy-Theme-Slug migrieren
        if settings.theme in _LEGACY_THEME_MAP:
            settings.theme = _LEGACY_THEME_MAP[settings.theme]
            with contextlib.suppress(Exception):
                settings.save()

        return settings
