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
            f"Entdeckt: [bold]{stats.total_discovered}[/bold]",
            f"Gecrawlt: [bold]{stats.total_crawled}[/bold]",
        ]
        if stats.total_errors > 0:
            parts.append(f"Fehler: [bold red]{stats.total_errors}[/bold red]")
        if stats.total_skipped > 0:
            parts.append(f"Skip: {stats.total_skipped}")

        parts.append(f"Queue: {stats.queue_size}")
        parts.append(f"Tiefe: {stats.max_depth_reached}")
        parts.append(stats.duration_display)

        self.update(" | ".join(parts))
