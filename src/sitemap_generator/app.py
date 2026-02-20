"""Hauptanwendung fuer Sitemap Generator."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime
from urllib.parse import urlparse

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, RichLog

from textual_themes import register_all

from . import __version__
from .models.crawl_result import CrawlResult, PageStatus
from .models.history import History, HistoryEntry
from .models.settings import Settings
from .services.crawler import Crawler
from .services.reporter import Reporter
from .models.sitemap_reader import discover_sitemap, load_sitemap_urls
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
    TITLE = f"Sitemap Generator v{__version__}"

    BINDINGS = [
        Binding("q", "quit", "Beenden"),
        Binding("s", "start_crawl", "Crawl"),
        Binding("x", "action_x", "Abbrechen"),
        Binding("m", "save_sitemap", "Sitemap erstellen"),
        Binding("o", "toggle_robots", "robots.txt AN"),
        Binding("p", "toggle_playwright", "Playwright AUS"),
        Binding("h", "show_history", "History"),
        Binding("e", "toggle_errors", "Nur Fehler"),
        Binding("j", "jira_report", "JIRA-Tabelle"),
        Binding("g", "save_forms", "Formulare"),
        Binding("b", "show_tree", "Seitenbaum"),
        Binding("f", "sitemap_diff", "Sitemap-Diff"),
        Binding("d", "copy_detail", "Details kopieren"),
        Binding("c", "copy_log", "Log kopieren"),
        Binding("l", "toggle_log", "Log"),
        Binding("plus", "log_bigger", "+", key_display="+"),
        Binding("minus", "log_smaller", "-", key_display="-"),
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

        # Retro-Themes registrieren (C64, Amiga, Atari ST, IBM Terminal, NeXTSTEP, BeOS)
        register_all(self)

        # Persistierte Einstellungen laden
        self._settings = Settings.load()

        self.start_url = start_url
        self.output_path = output_path
        self.max_depth = max_depth
        self.concurrency = concurrency
        self.timeout = timeout
        self.headless = headless
        self.user_agent = user_agent
        self.cookies = cookies or []

        # render/respect_robots: CLI ueberschreibt Settings
        # CLI --render setzt render=True, sonst aus Settings laden
        self.render = render if render else self._settings.render
        # CLI --ignore-robots setzt respect_robots=False, sonst aus Settings laden
        self.respect_robots = respect_robots if not respect_robots else self._settings.respect_robots

        # Theme aus Settings uebernehmen
        self.theme = self._settings.theme

        self._crawler: Crawler | None = None
        self._crawl_running: bool = False
        self._results: list[CrawlResult] = []
        self._official_sitemap_urls: set[str] = set()
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
        mode = "Playwright" if self.render else "httpx (schnell)"
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

        # Binding-Labels initial setzen
        self._update_robots_binding_label()
        self._update_playwright_binding_label()

        # Focus auf Tabelle
        try:
            from textual.widgets import DataTable
            table = self.query_one("#url-data", DataTable)
            table.focus()
        except Exception:
            pass

    def _update_robots_binding_label(self) -> None:
        """Aktualisiert das Binding-Label fuer robots.txt Toggle."""
        label = "robots.txt AN" if self.respect_robots else "robots.txt AUS"
        bindings_list = self._bindings.key_to_bindings.get("o", [])
        for i, binding in enumerate(bindings_list):
            if binding.action == "toggle_robots":
                self._bindings.key_to_bindings["o"][i] = dataclasses.replace(
                    binding, description=label
                )
                break
        self.refresh_bindings()

    def _update_playwright_binding_label(self) -> None:
        """Aktualisiert das Binding-Label fuer Playwright Toggle."""
        label = "Playwright AN" if self.render else "Playwright AUS"
        bindings_list = self._bindings.key_to_bindings.get("p", [])
        for i, binding in enumerate(bindings_list):
            if binding.action == "toggle_playwright":
                self._bindings.key_to_bindings["p"][i] = dataclasses.replace(
                    binding, description=label
                )
                break
        self.refresh_bindings()

    def _update_x_binding_label(self, label: str) -> None:
        """Aktualisiert das Binding-Label fuer die x-Taste.

        Args:
            label: Neues Label (z.B. "Abbrechen" oder "Fehlerbericht").
        """
        bindings_list = self._bindings.key_to_bindings.get("x", [])
        for i, binding in enumerate(bindings_list):
            if binding.action == "action_x":
                self._bindings.key_to_bindings["x"][i] = dataclasses.replace(
                    binding, description=label
                )
                break
        self.refresh_bindings()

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
        self._update_x_binding_label("Abbrechen")

        # URL-Tabelle leeren
        url_table = self.query_one("#url-table", UrlTable)
        url_table.clear_results()

        # Log einblenden und leeren
        log_widget = self.query_one("#crawl-log", RichLog)
        log_widget.remove_class("hidden")
        log_widget.clear()
        self._log_lines.clear()

        mode = "Playwright" if self.render else "httpx"
        self._write_log(f"\n[bold]Starte Crawl: {self.start_url}[/bold]")
        self._write_log(f"Modus: {mode} | Tiefe: {self.max_depth} | Concurrency: {self.concurrency}")

        # History-Eintrag speichern
        History.add(HistoryEntry(
            url=self.start_url,
            max_depth=self.max_depth,
            concurrency=self.concurrency,
            timeout=self.timeout,
            render=self.render,
            respect_robots=self.respect_robots,
            user_agent=self.user_agent,
            cookies=self.cookies,
        ))

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

        # Offizielle Sitemap autodiscovern (vor dem Crawl)
        self._official_sitemap_urls.clear()
        self._write_log("Suche offizielle Sitemap...")
        try:
            from .models.robots import RobotsChecker
            robots = RobotsChecker()
            await robots.load(self.start_url, cookies=self.cookies)
            robots_sitemaps = robots.sitemaps if robots.is_loaded else []

            sitemap_url = await discover_sitemap(
                self.start_url,
                robots_sitemaps=robots_sitemaps,
                cookies=self.cookies,
                log=on_log,
            )
            if sitemap_url:
                self._official_sitemap_urls = await load_sitemap_urls(
                    sitemap_url, cookies=self.cookies, log=on_log,
                )
                self._write_log(
                    f"[green]Offizielle Sitemap geladen: "
                    f"{len(self._official_sitemap_urls)} URLs[/green]"
                )
        except Exception as e:
            self._write_log(f"[yellow]Sitemap-Autodiscovery fehlgeschlagen: {e}[/yellow]")

        url_table.set_sitemap_urls(self._official_sitemap_urls)

        # Sitemap-URLs als Seed-URLs in den Crawler einspeisen,
        # damit auch nicht-verlinkte Seiten gecrawlt werden
        if self._official_sitemap_urls:
            added = self._crawler.add_seed_urls(self._official_sitemap_urls)
            if added:
                self._write_log(
                    f"[green]{added} Sitemap-URLs als Seed-URLs hinzugefuegt[/green]"
                )

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
            self._update_x_binding_label("JSON Fehlerbericht")

        if not self._crawler:
            # Abgebrochen
            self._write_log("[yellow]Crawl abgebrochen.[/yellow]")
            self.sub_title = "Abgebrochen"
            return

        stats = self._crawler.stats
        stats_panel.update_stats(stats)
        summary.update_stats(stats)

        http_200 = [r for r in self._results if r.http_status_code == 200]
        self._write_log(
            f"\n[bold green]Crawl abgeschlossen in {stats.duration_display}[/bold green]"
        )
        self._write_log(
            f"Gecrawlt: {stats.total_crawled} | "
            f"200er: {stats.total_2xx} | 300er: {stats.total_3xx} | "
            f"400er: {stats.total_4xx} | 500er: {stats.total_5xx} | "
            f"Fuer Sitemap: {len(http_200)}"
        )

        if stats.urls_per_second > 0:
            self._write_log(f"Geschwindigkeit: {stats.urls_per_second:.1f} URLs/Sek")

        self.sub_title = f"{stats.total_crawled} URLs gecrawlt"

        # Auto-Save wenn --output angegeben
        if self.output_path:
            self._do_save_sitemap(self.output_path)

        self._crawler = None

    def action_action_x(self) -> None:
        """Doppelbelegung: Waehrend Crawl abbrechen, danach Fehlerbericht erzeugen."""
        if self._crawl_running and self._crawler:
            self._do_cancel_crawl()
        elif self._results:
            self._do_save_error_report()

    def _do_cancel_crawl(self) -> None:
        """Bricht den laufenden Crawl ab."""
        if not self._crawl_running or not self._crawler:
            self.notify("Kein Crawl aktiv.", severity="warning")
            return

        self._crawler.cancel()
        self._write_log("[yellow]Crawl wird abgebrochen...[/yellow]")
        self.notify("Crawl wird abgebrochen...")

    def _do_save_error_report(self) -> None:
        """Erzeugt und speichert einen JSON-Fehlerbericht."""
        if not self._results:
            self.notify("Keine Ergebnisse vorhanden!", severity="warning")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hostname = urlparse(self.start_url).hostname or "unknown"
        hostname = hostname.replace(".", "-")
        filename = f"fehler_{hostname}_{timestamp}.json"

        errors = [r for r in self._results if r.is_error]
        if not errors:
            self._write_log("[green]Keine Fehler gefunden - kein Bericht noetig.[/green]")
            self.notify("Keine Fehler gefunden!", severity="information")
            return

        # Stats vom letzten Crawl holen
        from .models.crawl_result import CrawlStats
        stats = CrawlStats()
        # Stats aus den Ergebnissen rekonstruieren
        stats.total_crawled = len([r for r in self._results if r.status not in (PageStatus.PENDING, PageStatus.MAX_DEPTH, PageStatus.SKIPPED)])
        stats.total_discovered = len(self._results)
        for r in self._results:
            if r.http_status_code:
                cat = r.http_status_code // 100
                if cat == 2:
                    stats.total_2xx += 1
                elif cat == 3:
                    stats.total_3xx += 1
                elif cat == 4:
                    stats.total_4xx += 1
                elif cat == 5:
                    stats.total_5xx += 1
        stats.total_errors = stats.total_4xx + stats.total_5xx + len([
            r for r in self._results
            if r.status in (PageStatus.ERROR, PageStatus.TIMEOUT) and r.http_status_code < 400
        ])

        Reporter.save_error_report(self._results, stats, self.start_url, filename)
        self._write_log(f"[green]Fehlerbericht geschrieben: {filename} ({len(errors)} Fehler)[/green]")
        self.notify(f"Fehlerbericht: {filename} ({len(errors)} Fehler)")

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

        http_200 = [r for r in self._results if r.http_status_code == 200]
        for path in written:
            self._write_log(f"[green]Sitemap geschrieben: {path}[/green]")

        self.notify(f"Sitemap gespeichert: {written[0]} ({len(http_200)} URLs)")

    def action_toggle_robots(self) -> None:
        """Schaltet robots.txt-Beachtung um (AN/AUS)."""
        self.respect_robots = not self.respect_robots

        if self.respect_robots:
            self._write_log("[green]robots.txt wird beachtet[/green]")
        else:
            self._write_log("[yellow]robots.txt wird ignoriert[/yellow]")

        self._update_robots_binding_label()

        # Einstellung persistent speichern
        self._settings.respect_robots = self.respect_robots
        self._settings.save()

    def action_toggle_playwright(self) -> None:
        """Schaltet Playwright-Rendering um (AN/AUS)."""
        self.render = not self.render

        if self.render:
            self._write_log("[green]Playwright-Rendering aktiviert[/green]")
        else:
            self._write_log("[yellow]Playwright-Rendering deaktiviert (httpx)[/yellow]")

        self._update_playwright_binding_label()

        # Einstellung persistent speichern
        self._settings.render = self.render
        self._settings.save()

    def action_toggle_errors(self) -> None:
        """Schaltet den Error-Filter in der Tabelle um."""
        if not self._results:
            self.notify("Keine Ergebnisse vorhanden.", severity="warning")
            return

        url_table = self.query_one("#url-table", UrlTable)
        active = url_table.toggle_error_filter()

        # Detail-Panel zuruecksetzen (ausgewaehlte URL evtl. nicht mehr sichtbar)
        stats_panel = self.query_one("#stats-panel", StatsPanel)
        stats_panel.clear_detail()

        if active:
            self._write_log("[yellow]Zeige nur Fehler[/yellow]")
            self.notify("Filter: Nur Fehler")
        else:
            self._write_log("Zeige alle URLs")
            self.notify("Filter: Alle URLs")

    def action_copy_log(self) -> None:
        """Kopiert das Log in die Zwischenablage."""
        if not self._log_lines:
            self.notify("Log ist leer.", severity="warning")
            return

        # Rich-Markup entfernen fuer Clipboard
        import re
        clean_lines = []
        for line in self._log_lines:
            clean = re.sub(r"\[/?[^\]]*\]", "", line)
            clean_lines.append(clean)

        text = "\n".join(clean_lines)
        self.copy_to_clipboard(text)
        self.notify("Log in Zwischenablage kopiert")

    def action_show_history(self) -> None:
        """Zeigt den History-Dialog an."""
        from .screens.history import HistoryScreen
        self.push_screen(HistoryScreen(), self._on_history_selected)

    def _on_history_selected(self, entry: HistoryEntry | None) -> None:
        """Callback nach History-Auswahl.

        Args:
            entry: Der ausgewaehlte HistoryEntry oder None.
        """
        if entry is None:
            return

        self.start_url = entry.url
        self.max_depth = entry.max_depth
        self.concurrency = entry.concurrency
        self.timeout = entry.timeout
        self.render = entry.render
        self.respect_robots = entry.respect_robots
        self.cookies = entry.cookies
        if entry.user_agent:
            self.user_agent = entry.user_agent

        # UI aktualisieren
        mode = "Playwright" if self.render else "httpx (schnell)"
        summary = self.query_one("#summary", SummaryPanel)
        summary.set_info(self.start_url, mode)
        self.sub_title = self.start_url

        self._update_robots_binding_label()
        self._update_playwright_binding_label()

        self._write_log(
            f"[bold]History geladen: {self.start_url}[/bold]\n"
            f"  Modus: {mode} | Tiefe: {self.max_depth} | Concurrency: {self.concurrency}"
        )

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

    def action_jira_report(self) -> None:
        """Kopiert eine JIRA-Wiki-Tabelle mit Fehlern in die Zwischenablage."""
        if not self._results:
            self.notify("Keine Ergebnisse vorhanden!", severity="warning")
            return

        table_text = Reporter.generate_jira_table(self._results, self.start_url)

        if not table_text:
            self._write_log("[green]Keine Fehler gefunden - keine JIRA-Tabelle noetig.[/green]")
            self.notify("Keine Fehler gefunden!", severity="information")
            return

        self.copy_to_clipboard(table_text)
        error_count = len([r for r in self._results if r.is_error])
        self._write_log(f"[green]JIRA-Tabelle kopiert ({error_count} Fehler)[/green]")
        self.notify(f"JIRA-Tabelle kopiert ({error_count} Fehler)")

    def action_save_forms(self) -> None:
        """Exportiert alle Seiten mit Formularen als JSON-Datei."""
        if not self._results:
            self.notify("Keine Ergebnisse vorhanden!", severity="warning")
            return

        form_pages = [r for r in self._results if r.has_form and r.http_status_code == 200]
        if not form_pages:
            self._write_log("[green]Keine Formulare gefunden - kein Export noetig.[/green]")
            self.notify("Keine Formulare gefunden!", severity="information")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d")
        hostname = urlparse(self.start_url).hostname or "unknown"
        filename = f"formulare_{hostname}_{timestamp}.json"

        Reporter.save_forms_report(self._results, self.start_url, filename)
        self._write_log(f"[green]Formular-Report geschrieben: {filename} ({len(form_pages)} Seiten)[/green]")
        self.notify(f"Formulare: {filename} ({len(form_pages)} Seiten)")

    def action_show_tree(self) -> None:
        """Zeigt den Seitenbaum-Dialog an."""
        if not self._results:
            self.notify("Keine Ergebnisse vorhanden!", severity="warning")
            return

        from .screens.tree import TreeScreen
        self.push_screen(TreeScreen(
            self._results, self.start_url, self._official_sitemap_urls,
        ))

    def action_sitemap_diff(self) -> None:
        """Kopiert den Sitemap-Diff (fehlende/ueberfluessige URLs) in die Zwischenablage."""
        if not self._results:
            self.notify("Keine Ergebnisse vorhanden!", severity="warning")
            return

        if not self._official_sitemap_urls:
            self.notify("Keine offizielle Sitemap geladen!", severity="warning")
            return

        # Nur HTTP-200 Seiten vergleichen
        crawled_urls = {
            r.url for r in self._results
            if r.http_status_code == 200
        }

        not_in_sitemap = sorted(crawled_urls - self._official_sitemap_urls)
        not_crawled = sorted(self._official_sitemap_urls - crawled_urls)

        lines: list[str] = []
        lines.append(f"=== SITEMAP-DIFF ===")
        lines.append(f"Offizielle Sitemap: {len(self._official_sitemap_urls)} URLs")
        lines.append(f"Gecrawlt (200er): {len(crawled_urls)} URLs")
        lines.append("")

        lines.append(f"--- Gecrawlt aber NICHT in Sitemap ({len(not_in_sitemap)}) ---")
        for url in not_in_sitemap:
            lines.append(url)

        lines.append("")
        lines.append(f"--- In Sitemap aber NICHT gecrawlt ({len(not_crawled)}) ---")
        for url in not_crawled:
            lines.append(url)

        text = "\n".join(lines)
        self.copy_to_clipboard(text)
        self._write_log(
            f"[green]Sitemap-Diff kopiert: "
            f"{len(not_in_sitemap)} fehlend in Sitemap, "
            f"{len(not_crawled)} nicht gecrawlt[/green]"
        )
        self.notify(
            f"Sitemap-Diff: {len(not_in_sitemap)} fehlend, "
            f"{len(not_crawled)} nicht gecrawlt"
        )

    def action_copy_detail(self) -> None:
        """Kopiert die URL-Details der markierten URL in die Zwischenablage."""
        from .widgets.stats_panel import _sanitize_url

        stats_panel = self.query_one("#stats-panel", StatsPanel)
        result = stats_panel._selected_result

        if not result:
            self.notify("Keine URL ausgewaehlt!", severity="warning")
            return

        safe_url = _sanitize_url(result.url)
        lines = [
            f"URL: {safe_url}",
            f"Status: {result.status_icon} {result.status.value}",
        ]
        if result.redirect_url:
            lines.append(f"Redirect: {_sanitize_url(result.redirect_url)}")
        lines.extend([
            f"HTTP: {result.http_status_code if result.http_status_code else '-'}",
            f"Crawl-Tiefe: {result.depth}",
            f"Links: {result.links_found}",
            f"Ladezeit: {f'{result.load_time_ms:.0f}ms' if result.load_time_ms else '-'}",
        ])

        if result.content_type:
            lines.append(f"Content-Type: {result.content_type}")
        if result.last_modified:
            lines.append(f"Last-Modified: {result.last_modified}")
        if result.parent_url:
            lines.append(f"Parent: {_sanitize_url(result.parent_url)}")
        if result.error_message:
            lines.append(f"Fehler: {result.error_message}")

        if result.referring_pages:
            lines.append("")
            lines.append("Verweisende Seiten:")
            for ref in result.referring_pages:
                link_text = ref.get("link_text", "Link")
                ref_url = _sanitize_url(ref.get("url", ""))
                lines.append(f'  "{link_text}" \u2192 {ref_url}')

        text = "\n".join(lines)
        self.copy_to_clipboard(text)
        self.notify("URL-Details kopiert")

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
        if action == "action_x":
            if self._crawl_running:
                # Label: "Abbrechen"
                return True
            if self._results:
                # Label: "Fehlerbericht"
                return True
            return None
        if action == "start_crawl":
            return None if self._crawl_running else True
        if action == "save_sitemap":
            return True if self._results else None
        if action == "toggle_errors":
            return True if self._results else None
        if action in ("jira_report", "show_tree", "copy_detail", "save_forms"):
            return True if self._results else None
        if action == "sitemap_diff":
            return True if self._results and self._official_sitemap_urls else None
        if action == "show_history":
            return None if self._crawl_running else True
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
