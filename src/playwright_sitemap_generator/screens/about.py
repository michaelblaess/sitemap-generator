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
        width: 60;
        height: auto;
        max-height: 30;
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
            yield Static(f"Playwright Sitemap Generator v{__version__}", id="about-title")
            yield Static(
                "[bold]Tastenkuerzel:[/bold]\n"
                "\n"
                "  s = Crawl starten\n"
                "  x = Crawl abbrechen\n"
                "  r = Sitemap speichern\n"
                "  l = Log ein/aus\n"
                "  + = Log vergroessern\n"
                "  - = Log verkleinern\n"
                "  i = Info (dieser Dialog)\n"
                "  q = Beenden\n"
                "\n"
                "[bold]Modi:[/bold]\n"
                "  httpx (default) - Schnell, nur HTML-Parsing\n"
                "  --render - Playwright rendert JavaScript\n"
                "\n"
                "[dim]github.com/michaelblaess/playwright-sitemap-generator[/dim]",
                id="about-content",
            )
            yield Static("ESC = Schliessen", id="about-footer")

    def action_close(self) -> None:
        """Schliesst den Dialog."""
        self.dismiss()
