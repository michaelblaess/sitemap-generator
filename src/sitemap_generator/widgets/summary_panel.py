"""Summary-Panel Widget - Zeigt eine kompakte Zusammenfassung an."""

from __future__ import annotations

from textual.widgets import Static

from ..models.crawl_result import CrawlStats


class SummaryPanel(Static):
    """Kompakte einzeilige Zusammenfassung ueber der Tabelle."""

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)

    def set_info(self, url: str, mode: str) -> None:
        """Setzt die Basis-Info (URL und Modus).

        Args:
            url: Start-URL.
            mode: Crawl-Modus (httpx / Playwright).
        """
        self.update(f"[bold]{url}[/bold] | Modus: {mode}")

    def update_stats(self, stats: CrawlStats) -> None:
        """Aktualisiert die Statistik-Anzeige.

        Args:
            stats: Aktuelle CrawlStats.
        """
        parts = [
            f"Gecrawlt: [bold]{stats.total_crawled}[/bold]",
            f"200er: [green]{stats.total_2xx}[/green]",
            f"300er: [yellow]{stats.total_3xx}[/yellow]",
        ]
        if stats.total_4xx > 0:
            parts.append(f"400er: [bold red]{stats.total_4xx}[/bold red]")
        if stats.total_5xx > 0:
            parts.append(f"500er: [bold red]{stats.total_5xx}[/bold red]")

        parts.append(f"Queue: {stats.queue_size}")
        parts.append(stats.duration_display)

        self.update(" | ".join(parts))
