"""Persistente Einstellungen fuer den Sitemap Generator."""

from __future__ import annotations

import json
from pathlib import Path


# Einstellungsdatei im User-Verzeichnis
_SETTINGS_DIR = Path.home() / ".sitemap-generator"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"


class Settings:
    """Persistente Einstellungen (Theme etc.)."""

    def __init__(self) -> None:
        self.theme: str = "textual-dark"
        self.respect_robots: bool = True
        self.render: bool = False

    def save(self) -> None:
        """Speichert die Einstellungen in eine JSON-Datei."""
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "theme": self.theme,
            "respect_robots": self.respect_robots,
            "render": self.render,
        }
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> Settings:
        """Laedt die Einstellungen oder gibt Defaults zurueck.

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
            except Exception:
                pass
        return settings
