"""Settings-Dialog fuer den Sitemap Generator.

Erbt vom standardisierten `BaseSettingsScreen` (textual-widgets): die Basis
liefert Look, Sprach-Tab und Save/Cancel; diese Klasse ergaenzt nur den
Crawl-Tab mit den App-spezifischen Optionen.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Checkbox, Input, Label, Static, TabPane
from textual_widgets import BaseSettingsScreen

from ..i18n import t


class SitemapSettingsScreen(BaseSettingsScreen):
    """App-Settings: Sprache (von der Basis) + Crawl-Optionen."""

    def app_tabs(self) -> ComposeResult:
        """Ergaenzt den Crawl-Tab mit robots.txt, Playwright und Crawl-Parametern."""
        with TabPane(t("settings.tab_crawl"), id="settings-tab-crawl"):
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.robots_label"))
                yield Checkbox(
                    t("settings.robots_checkbox"),
                    value=bool(self._settings.get("respect_robots", True)),
                    id="set-robots",
                )
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.playwright_label"))
                yield Checkbox(
                    t("settings.playwright_checkbox"),
                    value=bool(self._settings.get("render", False)),
                    id="set-playwright",
                )
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.preview_label"))
                yield Checkbox(
                    t("settings.preview_checkbox"),
                    value=bool(self._settings.get("show_preview", False)),
                    id="set-preview",
                )
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.concurrency_label"))
                yield Input(
                    value=str(self._settings.get("concurrency", 8)),
                    type="integer",
                    id="set-concurrency",
                )
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.timeout_label"))
                yield Input(
                    value=str(self._settings.get("timeout", 30)),
                    type="integer",
                    id="set-timeout",
                )
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.max_depth_label"))
                yield Input(
                    value=str(self._settings.get("max_depth", 10)),
                    type="integer",
                    id="set-max-depth",
                )
            yield Static(t("settings.crawl_hint"), classes="settings-hint")

    def collect_app_settings(self, settings: dict[str, object]) -> None:
        """Schreibt die Crawl-Optionen aus den Widgets ins Ergebnis-Dict."""
        settings["respect_robots"] = self.query_one("#set-robots", Checkbox).value
        settings["render"] = self.query_one("#set-playwright", Checkbox).value
        settings["show_preview"] = self.query_one("#set-preview", Checkbox).value
        settings["concurrency"] = self._int("#set-concurrency", 8)
        settings["timeout"] = self._int("#set-timeout", 30)
        settings["max_depth"] = self._int("#set-max-depth", 10)

    def _int(self, selector: str, default: int) -> int:
        """Liest einen Integer-Wert aus einem Input-Feld (mit Fallback)."""
        try:
            return max(1, int(self.query_one(selector, Input).value))
        except (ValueError, TypeError):
            return default
