"""About-Dialog fuer den Sitemap Generator."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from .. import __version__


class AboutScreen(ModalScreen):
    """Zeigt Versionsinformationen und Tastenkuerzel."""

    DEFAULT_CSS = """
    AboutScreen {
        align: center middle;
    }

    AboutScreen > Vertical {
        width: 72;
        height: auto;
        max-height: 38;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }

    AboutScreen #about-title {
        height: 3;
        content-align: center middle;
        text-style: bold;
        background: $accent;
        color: $text;
        margin-bottom: 1;
    }

    AboutScreen #about-content {
        height: auto;
        padding: 1;
    }

    AboutScreen #about-footer {
        height: 1;
        content-align: center middle;
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Schliessen"),
        Binding("q", "close", "Schliessen"),
    ]

    def compose(self) -> ComposeResult:
        """Erstellt das About-Layout."""
        with Vertical():
            yield Static(f"Sitemap Generator v{__version__}", id="about-title")
            yield Static(
                "Crawlt eine Website rekursiv und erzeugt eine\n"
                "XML-Sitemap. Erkennt Dead Links (4xx/5xx),\n"
                "Timeouts und Redirect-Ketten.\n"
                "\n"
                "[bold]Features:[/bold]\n"
                "  - Zwei Modi: httpx (schnell) oder Playwright (JS)\n"
                "  - Dead-Link-Erkennung mit verweisenden Seiten\n"
                "  - JIRA-Tabelle und JSON-Fehlerbericht Export\n"
                "  - Seitenbaum mit Mermaid/ASCII Export\n"
                "  - robots.txt Beachtung (umschaltbar)\n"
                "  - Crawl-History mit Wiederholung\n"
                "\n"
                "[bold]Alle Tastenkuerzel sind in der Footer-Leiste\n"
                "am unteren Bildschirmrand sichtbar.[/bold]\n"
                "\n"
                "[dim italic]\"Wir muessen lernen, entweder als Brueder\n"
                " miteinander zu leben oder als Narren\n"
                " unterzugehen.\"\n"
                " - Martin Luther King Jr.[/dim italic]\n"
                "\n"
                "[dim]https://github.com/michaelblaess/sitemap-generator[/dim]",
                id="about-content",
            )
            yield Static("ESC = Schliessen", id="about-footer")

    def action_close(self) -> None:
        """Schliesst den Dialog."""
        self.dismiss()
