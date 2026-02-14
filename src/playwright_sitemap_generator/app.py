"""Hauptanwendung fuer Playwright Sitemap Generator."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, RichLog

from . import __version__
from .models.crawl_result import CrawlResult, PageStatus
from .models.settings import Settings
from .services.crawler import Crawler
from .models.sitemap_writer import SitemapWriter
from .widgets.stats_panel import StatsPanel
from .widgets.summary_panel import SummaryPanel
from .widgets.url_table import UrlTable


# Log-Hoehe: min/max/default (Zeilen)
LOG_HEIGHT_DEFAULT = 15
LOG_HEIGHT_MIN = 5
LOG_HEIGHT_MAX = 35
LOG_HEIGHT_STEP = 3


class SitemapGeneratorApp(App):
    """TUI-Anwendung zum Crawlen von Websites und Erzeugen von Sitemaps."""

    CSS_PATH = "app.tcss"
    TITLE = f"Playwright Sitemap Generator v{__version__}"

    BINDINGS = [
        Binding("q", "quit", "Beenden"),
        Binding("s", "start_crawl", "Crawl"),
        Binding("x", "cancel_crawl", "Abbrechen"),
        Binding("r", "save_sitemap", "Sitemap"),
        Binding("l", "toggle_log", "Log"),
        Binding("plus", "log_bigger", "Log +", key_display="+"),
        Binding("minus", "log_smaller", "Log -", key_display="-"),
        Binding("i", "show_about", "Info"),
    ]

    def __init__(
        self,
        start_url: str = "",
        output_path: str = "",
        max_depth: int = 10,
        concurrency: int = 8,
        timeout: int = 30,
        render: bool = False,
        headless: bool = True,
        respect_robots: bool = True,
        user_agent: str = "",
        cookies: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__()

        # Persistierte Einstellungen laden
        self._settings = Settings.load()

        self.start_url = start_url
        self.output_path = output_path
        self.max_depth = max_depth
        self.concurrency = concurrency
        self.timeout = timeout
        self.render = render
        self.headless = headless
        self.respect_robots = respect_robots
        self.user_agent = user_agent
        self.cookies = cookies or []

        # Theme aus Settings uebernehmen
        self.theme = self._settings.theme

        self._crawler: Crawler | None = None
        self._crawl_running: bool = False
        self._results: list[CrawlResult] = []
        self._log_lines: list[str] = []
        self._log_height: int = LOG_HEIGHT_DEFAULT
        self._stats_timer = None

    def compose(self) -> ComposeResult:
        """Erstellt das UI-Layout."""
        yield Header()
        yield SummaryPanel(id="summary")

        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield UrlTable(id="url-table")
                yield RichLog(id="crawl-log", highlight=True, markup=True)

            yield StatsPanel(id="stats-panel")

        yield Footer()

    def on_mount(self) -> None:
        """Initialisierung nach dem Starten."""
        mode = "Playwright (--render)" if self.render else "httpx (schnell)"
        robots_info = "AN" if self.respect_robots else "AUS"
        self._write_log(f"[bold]Playwright Sitemap Generator v{__version__}[/bold]")
        self._write_log(
            f"Modus: {mode} | Concurrency: {self.concurrency} | "
            f"Timeout: {self.timeout}s | Max-Tiefe: {self.max_depth} | "
            f"robots.txt: {robots_info}"
        )

        if self.start_url:
            summary = self.query_one("#summary", SummaryPanel)
            summary.set_info(self.start_url, mode)
            self.sub_title = self.start_url

        # Focus auf Tabelle
        try:
            from textual.widgets import DataTable
            table = self.query_one("#url-data", DataTable)
            table.focus()
        except Exception:
            pass

    @work(exclusive=True, group="crawl")
    async def action_start_crawl(self) -> None:
        """Startet den Crawl-Vorgang."""
        if self._crawl_running:
            self.notify("Crawl laeuft bereits!", severity="warning")
            return

        if not self.start_url:
            self.notify("Keine URL angegeben! Bitte URL als Parameter uebergeben.", severity="error")
            return

        self._crawl_running = True
        self._results.clear()

        # Log einblenden und leeren
        log_widget = self.query_one("#crawl-log", RichLog)
        log_widget.remove_class("hidden")
        log_widget.clear()
        self._log_lines.clear()

        mode = "Playwright" if self.render else "httpx"
        self._write_log(f"\n[bold]Starte Crawl: {self.start_url}[/bold]")
        self._write_log(f"Modus: {mode} | Tiefe: {self.max_depth} | Concurrency: {self.concurrency}")

        self._crawler = Crawler(
            start_url=self.start_url,
            max_depth=self.max_depth,
            concurrency=self.concurrency,
            timeout=self.timeout,
            render=self.render,
            headless=self.headless,
            respect_robots=self.respect_robots,
            cookies=self.cookies,
            user_agent=self.user_agent,
        )

        url_table = self.query_one("#url-table", UrlTable)
        stats_panel = self.query_one("#stats-panel", StatsPanel)
        summary = self.query_one("#summary", SummaryPanel)

        def on_result(result: CrawlResult) -> None:
            """Callback fuer jedes Crawl-Ergebnis."""
            url_table.update_result(result)
            stats_panel.update_stats(self._crawler.stats)
            summary.update_stats(self._crawler.stats)

        def on_log(msg: str) -> None:
            """Callback fuer Log-Nachrichten."""
            self._write_log(msg)

        self.sub_title = f"Crawling {self.start_url}..."

        try:
            self._results = await self._crawler.crawl(
                on_result=on_result,
                log=on_log,
            )
        except Exception as e:
            self._write_log(f"[red]Crawl-Fehler: {e}[/red]")
            self.notify(f"Crawl-Fehler: {e}", severity="error")
        finally:
            self._crawl_running = False

        if not self._crawler:
            # Abgebrochen
            self._write_log("[yellow]Crawl abgebrochen.[/yellow]")
            self.sub_title = "Abgebrochen"
            return

        stats = self._crawler.stats
        stats_panel.update_stats(stats)
        summary.update_stats(stats)

        successful = [r for r in self._results if r.is_successful]
        self._write_log(
            f"\n[bold green]Crawl abgeschlossen in {stats.duration_display}[/bold green]"
        )
        self._write_log(
            f"Entdeckt: {stats.total_discovered} | Gecrawlt: {stats.total_crawled} | "
            f"Fehler: {stats.total_errors} | Fuer Sitemap: {len(successful)}"
        )

        if stats.urls_per_second > 0:
            self._write_log(f"Geschwindigkeit: {stats.urls_per_second:.1f} URLs/Sek")

        self.sub_title = f"{stats.total_crawled} URLs gecrawlt"

        # Auto-Save wenn --output angegeben
        if self.output_path:
            self._do_save_sitemap(self.output_path)

        self._crawler = None

    def action_cancel_crawl(self) -> None:
        """Bricht den laufenden Crawl ab."""
        if not self._crawl_running or not self._crawler:
            self.notify("Kein Crawl aktiv.", severity="warning")
            return

        self._crawler.cancel()
        self._write_log("[yellow]Crawl wird abgebrochen...[/yellow]")
        self.notify("Crawl wird abgebrochen...")

    def action_save_sitemap(self) -> None:
        """Speichert die Sitemap als XML-Datei."""
        if not self._results:
            self.notify("Keine Ergebnisse vorhanden! Bitte zuerst crawlen.", severity="warning")
            return

        # Dateiname generieren
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hostname = urlparse(self.start_url).hostname or "unknown"
        hostname = hostname.replace(".", "-")
        filename = f"sitemap_{hostname}_{timestamp}.xml"

        self._do_save_sitemap(filename)

    def _do_save_sitemap(self, output_path: str) -> None:
        """Erzeugt und speichert die Sitemap.

        Args:
            output_path: Ausgabe-Pfad.
        """
        writer = SitemapWriter(self._results, base_url=self.start_url)
        written = writer.write(output_path)

        if not written:
            self._write_log("[yellow]Keine HTML-Seiten fuer Sitemap gefunden.[/yellow]")
            self.notify("Keine Seiten fuer Sitemap!", severity="warning")
            return

        successful = [r for r in self._results if r.is_successful]
        for path in written:
            self._write_log(f"[green]Sitemap geschrieben: {path}[/green]")

        self.notify(f"Sitemap gespeichert: {written[0]} ({len(successful)} URLs)")

    def on_url_table_url_highlighted(self, event: UrlTable.UrlHighlighted) -> None:
        """Aktualisiert das Stats-Panel bei Cursor-Bewegung."""
        stats_panel = self.query_one("#stats-panel", StatsPanel)
        stats_panel.show_url_detail(event.result)

    def action_toggle_log(self) -> None:
        """Blendet den Log-Bereich ein/aus."""
        log_widget = self.query_one("#crawl-log", RichLog)
        log_widget.toggle_class("hidden")

    def action_log_bigger(self) -> None:
        """Vergroessert den Log-Bereich."""
        self._log_height = min(self._log_height + LOG_HEIGHT_STEP, LOG_HEIGHT_MAX)
        log_widget = self.query_one("#crawl-log", RichLog)
        log_widget.styles.height = self._log_height

    def action_log_smaller(self) -> None:
        """Verkleinert den Log-Bereich."""
        self._log_height = max(self._log_height - LOG_HEIGHT_STEP, LOG_HEIGHT_MIN)
        log_widget = self.query_one("#crawl-log", RichLog)
        log_widget.styles.height = self._log_height

    def action_show_about(self) -> None:
        """Zeigt den About-Dialog an."""
        from .screens.about import AboutScreen
        self.push_screen(AboutScreen())

    def watch_theme(self, theme_name: str) -> None:
        """Speichert das Theme bei Aenderung persistent.

        Args:
            theme_name: Name des neuen Themes.
        """
        self._settings.theme = theme_name
        self._settings.save()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Steuert Sichtbarkeit von Bindings.

        Args:
            action: Name der Aktion.
            parameters: Aktionsparameter.

        Returns:
            True wenn sichtbar, None wenn versteckt.
        """
        if action == "cancel_crawl":
            return True if self._crawl_running else None
        if action == "start_crawl":
            return None if self._crawl_running else True
        if action == "save_sitemap":
            return True if self._results else None
        return True

    async def action_quit(self) -> None:
        """Beendet die App und raeumt auf."""
        if self._crawler:
            self._crawler.cancel()

            # Playwright TargetClosedError unterdruecken
            loop = asyncio.get_running_loop()
            original_handler = loop.get_exception_handler()

            def _suppress_target_closed(the_loop, context):
                exception = context.get("exception")
                if exception is not None:
                    exc_name = type(exception).__name__
                    if exc_name == "TargetClosedError":
                        return
                if original_handler:
                    original_handler(the_loop, context)
                else:
                    the_loop.default_exception_handler(context)

            loop.set_exception_handler(_suppress_target_closed)
            self._crawler = None
            self._crawl_running = False

        self.exit()

    def _write_log(self, line: str) -> None:
        """Schreibt eine Zeile ins Log-Widget und in den Puffer.

        Args:
            line: Log-Nachricht (kann Rich-Markup enthalten).
        """
        self._log_lines.append(line)
        try:
            self.query_one("#crawl-log", RichLog).write(line)
        except Exception:
            pass
