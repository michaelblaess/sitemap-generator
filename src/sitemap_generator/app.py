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
from .i18n import t
from .models.crawl_result import CrawlResult, PageStatus
from .models.history import History, HistoryEntry
from .models.settings import Settings
from .services.crawler import Crawler
from .services.reporter import Reporter
from .models.sitemap_reader import discover_sitemap, load_sitemap_urls, load_sitemap_from_file
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
        Binding("q", "quit", "placeholder"),
        Binding("s", "start_crawl", "placeholder"),
        Binding("x", "action_x", "placeholder"),
        Binding("m", "save_sitemap", "placeholder"),
        Binding("o", "toggle_robots", "placeholder"),
        Binding("p", "toggle_playwright", "placeholder"),
        Binding("h", "show_history", "placeholder"),
        Binding("e", "toggle_errors", "placeholder"),
        Binding("j", "jira_report", "placeholder"),
        Binding("g", "save_forms", "placeholder"),
        Binding("b", "show_tree", "placeholder"),
        Binding("f", "sitemap_diff", "placeholder"),
        Binding("d", "copy_detail", "placeholder"),
        Binding("c", "copy_log", "placeholder"),
        Binding("l", "toggle_log", "placeholder"),
        Binding("plus", "log_bigger", "+", key_display="+"),
        Binding("minus", "log_smaller", "-", key_display="-"),
        Binding("i", "show_about", "placeholder"),
    ]

    def __init__(
        self,
        start_url: str = "",
        sitemap_file: str = "",
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

        # Alle Retro-Themes aus textual-themes registrieren (31 Themes,
        # via Ctrl+P → "theme" auswaehlbar).
        register_all(self)

        # Persistierte Einstellungen laden
        self._settings = Settings.load()

        self.start_url = start_url
        self.sitemap_file = sitemap_file
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

        # Uebersetzte Binding-Labels setzen
        self._init_bindings()

    def _init_bindings(self) -> None:
        """Setzt die uebersetzten Labels fuer alle Bindings."""
        binding_labels = {
            "quit": t("binding.quit"),
            "start_crawl": t("binding.crawl"),
            "action_x": t("binding.cancel"),
            "save_sitemap": t("binding.save_sitemap"),
            "toggle_robots": t("binding.robots_on"),
            "toggle_playwright": t("binding.playwright_off"),
            "show_history": t("binding.history"),
            "toggle_errors": t("binding.errors_only"),
            "jira_report": t("binding.jira"),
            "save_forms": t("binding.forms"),
            "show_tree": t("binding.tree"),
            "sitemap_diff": t("binding.sitemap_diff"),
            "copy_detail": t("binding.copy_detail"),
            "copy_log": t("binding.copy_log"),
            "toggle_log": t("binding.log"),
            "show_about": t("binding.info"),
        }
        for key, bindings_list in self._bindings.key_to_bindings.items():
            for i, binding in enumerate(bindings_list):
                if binding.action in binding_labels:
                    self._bindings.key_to_bindings[key][i] = dataclasses.replace(
                        binding, description=binding_labels[binding.action]
                    )

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
        mode = t("mode.playwright") if self.render else t("mode.httpx")
        robots_info = t("log.robots_on") if self.respect_robots else t("log.robots_off")
        self._write_log(t("log.version", version=__version__))
        self._write_log(
            t("log.config", mode=mode, concurrency=self.concurrency,
              timeout=self.timeout, max_depth=self.max_depth, robots=robots_info)
        )

        if self.sitemap_file:
            import os
            filename = os.path.basename(self.sitemap_file)
            summary = self.query_one("#summary", SummaryPanel)
            summary.set_info(f"{t('log.file_label', filename=filename)}", mode)
            self.sub_title = filename
        elif self.start_url:
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
        label = t("binding.robots_on") if self.respect_robots else t("binding.robots_off")
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
        label = t("binding.playwright_on") if self.render else t("binding.playwright_off")
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
            self.notify(t("notify.crawl_running"), severity="warning")
            return

        # Lokale Sitemap-Datei: URLs laden und start_url daraus ermitteln
        if self.sitemap_file and not self.start_url:
            self._write_log(t("log.load_sitemap_file", path=self.sitemap_file))
            base_url, file_urls = load_sitemap_from_file(
                self.sitemap_file, log=lambda msg: self._write_log(msg),
            )
            if not file_urls:
                self.notify(t("notify.no_urls_in_file"), severity="error")
                return
            self.start_url = base_url
            self._file_seed_urls = file_urls

            # UI aktualisieren mit der ermittelten Basis-URL
            summary = self.query_one("#summary", SummaryPanel)
            mode = t("mode.playwright") if self.render else t("mode.httpx")
            summary.set_info(self.start_url, mode)

        if not self.start_url:
            self.notify(t("notify.no_url"), severity="error")
            return

        self._crawl_running = True
        self._results.clear()
        self._update_x_binding_label(t("binding.cancel"))

        # URL-Tabelle leeren
        url_table = self.query_one("#url-table", UrlTable)
        url_table.clear_results()

        # Log einblenden und leeren
        log_widget = self.query_one("#crawl-log", RichLog)
        log_widget.remove_class("hidden")
        log_widget.clear()
        self._log_lines.clear()

        mode = t("mode.playwright") if self.render else t("mode.httpx_short")
        self._write_log(t("log.start_crawl", url=self.start_url))
        self._write_log(t("log.crawl_config", mode=mode, max_depth=self.max_depth, concurrency=self.concurrency))

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
        self._write_log(t("log.searching_sitemap"))
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
                    t("log.official_sitemap_loaded", count=len(self._official_sitemap_urls))
                )
        except Exception as e:
            self._write_log(t("log.sitemap_autodiscovery_failed", error=e))

        url_table.set_sitemap_urls(self._official_sitemap_urls)

        # Sitemap-URLs als Seed-URLs in den Crawler einspeisen,
        # damit auch nicht-verlinkte Seiten gecrawlt werden
        if self._official_sitemap_urls:
            added = self._crawler.add_seed_urls(self._official_sitemap_urls)
            if added:
                self._write_log(t("log.seed_urls_sitemap", count=added))

        # URLs aus lokaler Datei als Seed-URLs einspeisen
        if hasattr(self, "_file_seed_urls") and self._file_seed_urls:
            added = self._crawler.add_seed_urls(self._file_seed_urls)
            if added:
                self._write_log(t("log.seed_urls_file", count=added))
            self._file_seed_urls = set()  # Nach Verwendung leeren

        self.sub_title = t("subtitle.crawling", url=self.start_url)

        try:
            self._results = await self._crawler.crawl(
                on_result=on_result,
                log=on_log,
            )
        except Exception as e:
            self._write_log(t("log.crawl_error", error=e))
            self.notify(t("notify.crawl_error", error=e), severity="error")
        finally:
            self._crawl_running = False
            self._update_x_binding_label(t("binding.error_report"))

        if not self._crawler:
            # Abgebrochen
            self._write_log(t("log.crawl_cancelled"))
            self.sub_title = t("subtitle.cancelled")
            return

        stats = self._crawler.stats
        stats_panel.update_stats(stats)
        summary.update_stats(stats)

        http_200 = [r for r in self._results if r.http_status_code == 200]
        self._write_log(t("log.crawl_complete", duration=stats.duration_display))
        self._write_log(
            t("log.crawl_stats",
              crawled=stats.total_crawled, s2xx=stats.total_2xx,
              s3xx=stats.total_3xx, s4xx=stats.total_4xx,
              s5xx=stats.total_5xx, sitemap=len(http_200))
        )

        if stats.urls_per_second > 0:
            self._write_log(t("log.crawl_speed", speed=stats.urls_per_second))

        self.sub_title = t("subtitle.crawled", count=stats.total_crawled)

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
            self.notify(t("notify.no_crawl_active"), severity="warning")
            return

        self._crawler.cancel()
        self._write_log(t("log.cancel_crawl"))
        self.notify(t("notify.crawl_cancelling"))

    def _do_save_error_report(self) -> None:
        """Erzeugt und speichert einen JSON-Fehlerbericht."""
        if not self._results:
            self.notify(t("notify.no_results"), severity="warning")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hostname = urlparse(self.start_url).hostname or "unknown"
        hostname = hostname.replace(".", "-")
        filename = f"fehler_{hostname}_{timestamp}.json"

        errors = [r for r in self._results if r.is_error]
        if not errors:
            self._write_log(t("log.no_errors_report"))
            self.notify(t("notify.no_errors"), severity="information")
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
        self._write_log(t("log.error_report_written", filename=filename, count=len(errors)))
        self.notify(t("notify.error_report", filename=filename, count=len(errors)))

    def action_save_sitemap(self) -> None:
        """Speichert die Sitemap als XML-Datei."""
        if not self._results:
            self.notify(t("notify.no_results_crawl"), severity="warning")
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
            self._write_log(t("log.no_pages_sitemap"))
            self.notify(t("notify.no_pages_for_sitemap"), severity="warning")
            return

        http_200 = [r for r in self._results if r.http_status_code == 200]
        for path in written:
            self._write_log(t("log.sitemap_written", path=path))

        self.notify(t("notify.sitemap_saved", path=written[0], count=len(http_200)))

    def action_toggle_robots(self) -> None:
        """Schaltet robots.txt-Beachtung um (AN/AUS)."""
        self.respect_robots = not self.respect_robots

        if self.respect_robots:
            self._write_log(t("log.robots_respected"))
        else:
            self._write_log(t("log.robots_ignored"))

        self._update_robots_binding_label()

        # Einstellung persistent speichern
        self._settings.respect_robots = self.respect_robots
        self._settings.save()

    def action_toggle_playwright(self) -> None:
        """Schaltet Playwright-Rendering um (AN/AUS)."""
        self.render = not self.render

        if self.render:
            self._write_log(t("log.playwright_on"))
        else:
            self._write_log(t("log.playwright_off"))

        self._update_playwright_binding_label()

        # Einstellung persistent speichern
        self._settings.render = self.render
        self._settings.save()

    def action_toggle_errors(self) -> None:
        """Schaltet den Error-Filter in der Tabelle um."""
        if not self._results:
            self.notify(t("notify.no_results_dot"), severity="warning")
            return

        url_table = self.query_one("#url-table", UrlTable)
        active = url_table.toggle_error_filter()

        # Detail-Panel zuruecksetzen (ausgewaehlte URL evtl. nicht mehr sichtbar)
        stats_panel = self.query_one("#stats-panel", StatsPanel)
        stats_panel.clear_detail()

        if active:
            self._write_log(t("log.filter_errors"))
            self.notify(t("notify.filter_errors"))
        else:
            self._write_log(t("log.filter_all"))
            self.notify(t("notify.filter_all"))

    def action_copy_log(self) -> None:
        """Kopiert das Log in die Zwischenablage."""
        if not self._log_lines:
            self.notify(t("notify.log_empty"), severity="warning")
            return

        # Rich-Markup entfernen fuer Clipboard
        import re
        clean_lines = []
        for line in self._log_lines:
            clean = re.sub(r"\[/?[^\]]*\]", "", line)
            clean_lines.append(clean)

        text = "\n".join(clean_lines)
        self.copy_to_clipboard(text)
        self.notify(t("notify.log_copied"))

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
        mode = t("mode.playwright") if self.render else t("mode.httpx")
        summary = self.query_one("#summary", SummaryPanel)
        summary.set_info(self.start_url, mode)
        self.sub_title = self.start_url

        self._update_robots_binding_label()
        self._update_playwright_binding_label()

        self._write_log(
            t("log.history_loaded", url=self.start_url, mode=mode,
              max_depth=self.max_depth, concurrency=self.concurrency)
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
            self.notify(t("notify.no_results"), severity="warning")
            return

        table_text = Reporter.generate_jira_table(self._results, self.start_url)

        if not table_text:
            self._write_log(t("log.no_errors_jira"))
            self.notify(t("notify.no_errors"), severity="information")
            return

        self.copy_to_clipboard(table_text)
        error_count = len([r for r in self._results if r.is_error])
        self._write_log(t("log.jira_copied", count=error_count))
        self.notify(t("notify.jira_copied", count=error_count))

    def action_save_forms(self) -> None:
        """Exportiert alle Seiten mit Formularen als JSON-Datei."""
        if not self._results:
            self.notify(t("notify.no_results"), severity="warning")
            return

        form_pages = [r for r in self._results if r.has_form and r.http_status_code == 200]
        if not form_pages:
            self._write_log(t("log.no_forms"))
            self.notify(t("notify.no_forms"), severity="information")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d")
        hostname = urlparse(self.start_url).hostname or "unknown"
        filename = f"formulare_{hostname}_{timestamp}.json"

        Reporter.save_forms_report(self._results, self.start_url, filename)
        self._write_log(t("log.forms_written", filename=filename, count=len(form_pages)))
        self.notify(t("notify.forms_saved", filename=filename, count=len(form_pages)))

    def action_show_tree(self) -> None:
        """Zeigt den Seitenbaum-Dialog an."""
        if not self._results:
            self.notify(t("notify.no_results"), severity="warning")
            return

        from .screens.tree import TreeScreen
        self.push_screen(TreeScreen(
            self._results, self.start_url, self._official_sitemap_urls,
        ))

    def action_sitemap_diff(self) -> None:
        """Kopiert den Sitemap-Diff (fehlende/ueberfluessige URLs) in die Zwischenablage."""
        if not self._results:
            self.notify(t("notify.no_results"), severity="warning")
            return

        if not self._official_sitemap_urls:
            self.notify(t("notify.no_official_sitemap"), severity="warning")
            return

        # Nur HTTP-200 Seiten vergleichen
        crawled_urls = {
            r.url for r in self._results
            if r.http_status_code == 200
        }

        not_in_sitemap = sorted(crawled_urls - self._official_sitemap_urls)
        not_crawled = sorted(self._official_sitemap_urls - crawled_urls)

        lines: list[str] = []
        lines.append(t("diff.header"))
        lines.append(t("diff.official_count", count=len(self._official_sitemap_urls)))
        lines.append(t("diff.crawled_count", count=len(crawled_urls)))
        lines.append("")

        lines.append(t("diff.not_in_sitemap", count=len(not_in_sitemap)))
        for url in not_in_sitemap:
            lines.append(url)

        lines.append("")
        lines.append(t("diff.not_crawled", count=len(not_crawled)))
        for url in not_crawled:
            lines.append(url)

        text = "\n".join(lines)
        self.copy_to_clipboard(text)
        self._write_log(
            t("log.sitemap_diff_copied",
              missing=len(not_in_sitemap), not_crawled=len(not_crawled))
        )
        self.notify(
            t("notify.sitemap_diff",
              missing=len(not_in_sitemap), not_crawled=len(not_crawled))
        )

    def action_copy_detail(self) -> None:
        """Kopiert die URL-Details der markierten URL in die Zwischenablage."""
        from .widgets.stats_panel import _sanitize_url

        stats_panel = self.query_one("#stats-panel", StatsPanel)
        result = stats_panel._selected_result

        if not result:
            self.notify(t("notify.no_url_selected"), severity="warning")
            return

        safe_url = _sanitize_url(result.url)
        lines = [
            t("copy.url", url=safe_url),
            t("copy.status", icon=result.status_icon, status=result.status.value),
        ]
        if result.redirect_url:
            lines.append(t("copy.redirect", url=_sanitize_url(result.redirect_url)))
        lines.extend([
            t("copy.http", code=result.http_status_code if result.http_status_code else '-'),
            t("copy.depth", depth=result.depth),
            t("copy.links", count=result.links_found),
            t("copy.load_time", time=f'{result.load_time_ms:.0f}ms' if result.load_time_ms else '-'),
        ])

        if result.content_type:
            lines.append(f"Content-Type: {result.content_type}")
        if result.last_modified:
            lines.append(f"Last-Modified: {result.last_modified}")
        if result.parent_url:
            lines.append(f"Parent: {_sanitize_url(result.parent_url)}")
        if result.error_message:
            lines.append(t("copy.error", message=result.error_message))

        if result.referring_pages:
            lines.append("")
            lines.append(t("copy.referring_pages"))
            for ref in result.referring_pages:
                link_text = ref.get("link_text", "Link")
                ref_url = _sanitize_url(ref.get("url", ""))
                lines.append(f'  "{link_text}" \u2192 {ref_url}')

        text = "\n".join(lines)
        self.copy_to_clipboard(text)
        self.notify(t("notify.details_copied"))

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
                return True
            if self._results:
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
