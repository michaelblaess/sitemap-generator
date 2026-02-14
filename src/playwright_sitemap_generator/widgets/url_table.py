"""URL-Tabelle Widget - Zeigt gecrawlte URLs mit Status an."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import DataTable, Static

from ..models.crawl_result import CrawlResult, PageStatus


class UrlTable(Static):
    """Tabelle aller entdeckten URLs mit Live-Status-Updates."""

    class UrlHighlighted(Message):
        """Wird gesendet wenn eine URL in der Tabelle markiert wird."""
        def __init__(self, result: CrawlResult) -> None:
            super().__init__()
            self.result = result

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._results: list[CrawlResult] = []
        self._url_to_row: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        """Erstellt die DataTable."""
        table = DataTable(id="url-data", cursor_type="row")
        table.add_columns("St", "HTTP", "Tiefe", "Links", "Zeit", "URL")
        yield table

    def load_results(self, results: list[CrawlResult]) -> None:
        """Laedt alle Ergebnisse in die Tabelle.

        Args:
            results: Liste der CrawlResults.
        """
        self._results = results
        self._url_to_row.clear()

        table = self.query_one("#url-data", DataTable)
        table.clear()

        for idx, result in enumerate(results):
            table.add_row(
                result.status_icon,
                str(result.http_status_code) if result.http_status_code else "-",
                str(result.depth),
                str(result.links_found) if result.links_found else "-",
                f"{result.load_time_ms:.0f}ms" if result.load_time_ms else "-",
                result.url,
                key=result.url,
            )
            self._url_to_row[result.url] = idx

    def update_result(self, result: CrawlResult) -> None:
        """Aktualisiert eine einzelne Zeile in der Tabelle.

        Args:
            result: Das aktualisierte CrawlResult.
        """
        table = self.query_one("#url-data", DataTable)

        try:
            row_key = table.get_row(result.url)
        except Exception:
            # URL noch nicht in Tabelle -> hinzufuegen
            table.add_row(
                result.status_icon,
                str(result.http_status_code) if result.http_status_code else "-",
                str(result.depth),
                str(result.links_found) if result.links_found else "-",
                f"{result.load_time_ms:.0f}ms" if result.load_time_ms else "-",
                result.url,
                key=result.url,
            )
            self._url_to_row[result.url] = len(self._results)
            if result not in self._results:
                self._results.append(result)
            return

        # Bestehende Zeile aktualisieren
        col_keys = list(table.columns.keys())
        table.update_cell(result.url, col_keys[0], result.status_icon)
        table.update_cell(result.url, col_keys[1], str(result.http_status_code) if result.http_status_code else "-")
        table.update_cell(result.url, col_keys[2], str(result.depth))
        table.update_cell(result.url, col_keys[3], str(result.links_found) if result.links_found else "-")
        table.update_cell(result.url, col_keys[4], f"{result.load_time_ms:.0f}ms" if result.load_time_ms else "-")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Sendet ein UrlHighlighted-Event bei Cursor-Bewegung."""
        if event.row_key and event.row_key.value:
            url = event.row_key.value
            for result in self._results:
                if result.url == url:
                    self.post_message(self.UrlHighlighted(result))
                    break
