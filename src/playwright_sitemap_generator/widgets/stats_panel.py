"""Statistik-Panel Widget - Zeigt Crawl-Fortschritt und Statistiken an."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from textual.app import ComposeResult
from textual.widgets import Static

from ..models.crawl_result import CrawlResult, CrawlStats, PageStatus


class StatsPanel(Static):
    """Panel mit Live-Crawl-Statistiken und URL-Detail-Ansicht."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stats = CrawlStats()
        self._selected_result: CrawlResult | None = None

    def compose(self) -> ComposeResult:
        """Erstellt das Panel-Layout."""
        yield Static("Bereit - URL eingeben und [bold]s[/bold] druecken", id="stats-content")
        yield Static("", id="url-detail")

    def update_stats(self, stats: CrawlStats) -> None:
        """Aktualisiert die Crawl-Statistiken.

        Args:
            stats: Aktuelle CrawlStats.
        """
        self._stats = stats

        table = Table(show_header=False, expand=True, box=None, padding=(0, 1))
        table.add_column("Key", style="bold", width=18)
        table.add_column("Value")

        table.add_row("Entdeckt", str(stats.total_discovered))
        table.add_row("Gecrawlt", str(stats.total_crawled))
        table.add_row("Fehler", f"[red]{stats.total_errors}[/red]" if stats.total_errors else "0")
        table.add_row("Uebersprungen", str(stats.total_skipped))
        table.add_row("Queue", str(stats.queue_size))
        table.add_row("Max Tiefe", str(stats.max_depth_reached))
        table.add_row("Dauer", stats.duration_display)

        if stats.urls_per_second > 0:
            table.add_row("URLs/Sek", f"{stats.urls_per_second:.1f}")

        content = self.query_one("#stats-content", Static)
        content.update(table)

    def show_url_detail(self, result: CrawlResult) -> None:
        """Zeigt Detail-Infos zur markierten URL.

        Args:
            result: Das CrawlResult der markierten URL.
        """
        self._selected_result = result

        detail_table = Table(show_header=False, expand=True, box=None, padding=(0, 1))
        detail_table.add_column("Key", style="dim", width=18)
        detail_table.add_column("Value")

        detail_table.add_row("URL", Text(result.url, style="bold", overflow="ellipsis"))
        detail_table.add_row("Status", result.status_icon + " " + result.status.value)
        detail_table.add_row("HTTP", str(result.http_status_code) if result.http_status_code else "-")
        detail_table.add_row("Tiefe", str(result.depth))
        detail_table.add_row("Links", str(result.links_found))
        detail_table.add_row("Ladezeit", f"{result.load_time_ms:.0f}ms" if result.load_time_ms else "-")

        if result.content_type:
            detail_table.add_row("Content-Type", result.content_type)
        if result.last_modified:
            detail_table.add_row("Last-Modified", result.last_modified)
        if result.parent_url:
            detail_table.add_row("Parent", Text(result.parent_url, overflow="ellipsis"))
        if result.error_message:
            detail_table.add_row("Fehler", Text(result.error_message, style="red"))

        detail = self.query_one("#url-detail", Static)
        detail.update(detail_table)
