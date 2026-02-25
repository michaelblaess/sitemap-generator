"""URL-Tabelle Widget - Zeigt gecrawlte URLs mit Status und Farbcodierung an."""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import DataTable, Input, Static

from ..models.crawl_result import CrawlResult, PageStatus


# Spinner-Frames fuer CRAWLING-Status
SPINNER_FRAMES = [">  ", ">> ", ">>>", " >>", "  >", "   "]


class UrlTable(Static):
    """Tabelle aller entdeckten URLs mit Live-Status-Updates und Farbcodierung."""

    DEFAULT_CSS = """
    UrlTable #results-count {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    UrlTable #filter-bar {
        dock: top;
        height: 3;
        padding: 0 1;
    }

    UrlTable DataTable {
        height: 1fr;
    }
    """

    # Tasten bei denen Auto-Scroll deaktiviert wird (manuelle Navigation)
    _NAV_KEYS = {"up", "down", "pageup", "pagedown", "home", "end"}

    class UrlHighlighted(Message):
        """Wird gesendet wenn eine URL in der Tabelle markiert wird."""
        def __init__(self, result: CrawlResult) -> None:
            super().__init__()
            self.result = result

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._results: list[CrawlResult] = []
        self._filtered: list[CrawlResult] = []
        self._col_keys: list = []
        self._show_only_errors: bool = False
        self._filter_text: str = ""
        self._row_counter: int = 0
        self._spinner_frame: int = 0
        self._spinner_timer = None
        self._sitemap_urls: set[str] = set()
        self._auto_scroll: bool = True
        self._auto_scroll_row: int = -1

    def compose(self) -> ComposeResult:
        """Erstellt die DataTable mit Filter-Eingabe."""
        yield Static("", id="results-count")
        yield Input(placeholder="Filter (URL, Status...)", id="filter-bar")
        yield DataTable(id="url-data", cursor_type="row")

    def on_mount(self) -> None:
        """Initialisiert die Tabellenspalten und startet den Spinner-Timer."""
        table = self.query_one("#url-data", DataTable)
        self._col_keys = table.add_columns(
            "#", "Status", "HTTP", "Tiefe", "Links", "Formular (?)", "Zeit", "URL",
        )
        self._spinner_timer = self.set_interval(0.3, self._tick_spinner)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Reagiert auf Aenderungen im Filter-Input.

        Args:
            event: Das Input.Changed-Event.
        """
        if event.input.id == "filter-bar":
            self._filter_text = event.value
            self._apply_filter()

    def _tick_spinner(self) -> None:
        """Aktualisiert den Spinner-Frame der CRAWLING-Zeilen in-place."""
        has_crawling = any(
            r.status == PageStatus.CRAWLING for r in self._filtered
        )
        if not has_crawling:
            return
        self._spinner_frame = (self._spinner_frame + 1) % len(SPINNER_FRAMES)
        table = self.query_one("#url-data", DataTable)
        for idx, result in enumerate(self._filtered):
            if result.status == PageStatus.CRAWLING:
                table.update_cell(
                    result.url, self._col_keys[1], self._status_cell(result),
                )

    def _status_cell(self, result: CrawlResult) -> Text:
        """Erzeugt eine farbcodierte Zelle fuer den Status.

        Args:
            result: Das CrawlResult.

        Returns:
            Rich Text mit Label und Farbe (z.B. ERR rot, OK gruen).
        """
        if result.status == PageStatus.CRAWLING:
            frame = SPINNER_FRAMES[self._spinner_frame]
            return Text(frame, style="bold cyan")
        label, style = result.status_label
        return Text(label, style=style)

    @staticmethod
    def _http_status_cell(code: int) -> Text | str:
        """Erzeugt eine farbcodierte Zelle fuer den HTTP-Statuscode.

        Args:
            code: HTTP-Statuscode.

        Returns:
            Rich Text mit passender Farbe oder "-".
        """
        if not code:
            return "-"
        category = code // 100
        code_str = str(code)
        if category == 2:
            return Text(code_str, style="green")
        if category == 3:
            return Text(code_str, style="yellow")
        if category >= 4:
            return Text(code_str, style="bold red")
        return code_str

    def _url_cell(self, result: CrawlResult) -> Text | str:
        """Erzeugt eine farbcodierte Zelle fuer die URL.

        Externe Redirects: dim (ausgegraut).
        HTTP-200 Seiten nicht in offizieller Sitemap: orange markiert.

        Args:
            result: Das CrawlResult.

        Returns:
            Rich Text oder einfacher String.
        """
        if result.is_external_redirect:
            return Text(result.url, style="dim")
        if (
            self._sitemap_urls
            and result.http_status_code == 200
            and result.url not in self._sitemap_urls
        ):
            return Text(result.url, style="dark_orange")
        return result.url

    def set_sitemap_urls(self, urls: set[str]) -> None:
        """Setzt die offizielle Sitemap-URL-Liste fuer farbliche Markierung.

        Args:
            urls: Set der URLs aus der offiziellen Sitemap.
        """
        self._sitemap_urls = urls
        if self._results:
            self._refresh_table()

    def _matches_filter(self, result: CrawlResult) -> bool:
        """Prueft ob ein Ergebnis dem aktuellen Filter entspricht.

        Args:
            result: Das zu pruefende CrawlResult.

        Returns:
            True wenn das Ergebnis angezeigt werden soll.
        """
        if self._show_only_errors and not result.is_error:
            return False
        if self._filter_text:
            search = self._filter_text.lower()
            label, _ = result.status_label
            # "form" als Suchbegriff matcht Seiten mit Formularen
            form_match = result.has_form if search == "form" else False
            if (
                search not in result.url.lower()
                and search not in label.lower()
                and search not in str(result.http_status_code)
                and not form_match
            ):
                return False
        return True

    def _apply_filter(self) -> None:
        """Wendet den aktuellen Filter an und aktualisiert die Tabelle."""
        self._filtered = [r for r in self._results if self._matches_filter(r)]
        self._refresh_table()

    def _update_row_cells(self, table: DataTable, result: CrawlResult) -> None:
        """Aktualisiert alle Zellen einer Zeile in-place.

        Args:
            table: Die DataTable-Instanz.
            result: Das aktualisierte CrawlResult.
        """
        row_key = result.url
        form_cell = Text("JA", style="green") if result.has_form else Text("-", style="dim")
        table.update_cell(row_key, self._col_keys[1], self._status_cell(result))
        table.update_cell(row_key, self._col_keys[2], self._http_status_cell(result.http_status_code))
        table.update_cell(row_key, self._col_keys[3], str(result.depth))
        table.update_cell(row_key, self._col_keys[4], str(result.links_found) if result.links_found else "-")
        table.update_cell(row_key, self._col_keys[5], form_cell)
        table.update_cell(row_key, self._col_keys[6], f"{result.load_time_ms / 1000:.1f}s" if result.load_time_ms else "-")
        table.update_cell(row_key, self._col_keys[7], self._url_cell(result))

    def _refresh_table(self) -> None:
        """Baut die DataTable komplett neu auf (clear + rebuild).

        Wird nur bei strukturellen Aenderungen verwendet (load_results,
        Filter-Wechsel).  Waehrend des Crawls nutzt update_result()
        stattdessen _update_row_cells() fuer in-place Updates.
        """
        table = self.query_one("#url-data", DataTable)
        saved_row = table.cursor_row
        table.clear()
        self._row_counter = 0

        for result in self._filtered:
            self._row_counter += 1
            url_cell = self._url_cell(result)
            form_cell = Text("JA", style="green") if result.has_form else Text("-", style="dim")
            table.add_row(
                str(self._row_counter),
                self._status_cell(result),
                self._http_status_cell(result.http_status_code),
                str(result.depth),
                str(result.links_found) if result.links_found else "-",
                form_cell,
                f"{result.load_time_ms / 1000:.1f}s" if result.load_time_ms else "-",
                url_cell,
                key=result.url,
            )

        # Cursor wiederherstellen
        if self._auto_scroll and 0 <= self._auto_scroll_row < len(self._filtered):
            target_row = self._auto_scroll_row
        elif saved_row >= 0 and len(self._filtered) > 0:
            target_row = min(saved_row, len(self._filtered) - 1)
        else:
            target_row = -1

        if target_row >= 0:
            table.move_cursor(row=target_row)

        self._update_count_label()

    def _update_count_label(self) -> None:
        """Aktualisiert das Zaehler-Label."""
        total = len(self._results)
        shown = len(self._filtered)
        count_label = self.query_one("#results-count", Static)
        if total == shown:
            count_label.update(f" {total} URLs")
        else:
            count_label.update(f" {shown} von {total} URLs (gefiltert)")

    def clear_results(self) -> None:
        """Leert alle Ergebnisse und die Tabelle."""
        self._results.clear()
        self._filtered.clear()
        self._row_counter = 0
        self._filter_text = ""
        self._auto_scroll = True
        self._auto_scroll_row = -1
        table = self.query_one("#url-data", DataTable)
        table.clear()
        self._update_count_label()

    def load_results(self, results: list[CrawlResult]) -> None:
        """Laedt alle Ergebnisse in die Tabelle.

        Setzt Auto-Scroll zurueck, damit beim naechsten Crawl
        automatisch zur aktuellen Zeile gescrollt wird.

        Args:
            results: Liste der CrawlResults.
        """
        self._results = results
        self._auto_scroll = True
        self._auto_scroll_row = -1
        self._apply_filter()

    def update_result(self, result: CrawlResult) -> None:
        """Aktualisiert eine einzelne Zeile in der Tabelle.

        Aktualisiert Zellen in-place (kein clear/rebuild), damit die
        Scroll-Position erhalten bleibt.  Bei aktivem Filter wird
        ein vollstaendiger Rebuild durchgefuehrt falls sich die
        Tabellenstruktur aendern koennte.

        Args:
            result: Das aktualisierte CrawlResult.
        """
        is_new = result not in self._results
        if is_new:
            self._results.append(result)

        if self._show_only_errors or self._filter_text:
            # Filter aktiv - Struktur koennte sich aendern
            self._filtered = [r for r in self._results if self._matches_filter(r)]
            if self._auto_scroll:
                self._scroll_to_result(result)
            self._refresh_table()
            return

        # Kein Filter aktiv
        if is_new:
            # Neue Zeile hinzufuegen (kein clear/rebuild)
            self._filtered.append(result)
            self._row_counter += 1
            table = self.query_one("#url-data", DataTable)
            form_cell = Text("JA", style="green") if result.has_form else Text("-", style="dim")
            table.add_row(
                str(self._row_counter),
                self._status_cell(result),
                self._http_status_cell(result.http_status_code),
                str(result.depth),
                str(result.links_found) if result.links_found else "-",
                form_cell,
                f"{result.load_time_ms / 1000:.1f}s" if result.load_time_ms else "-",
                self._url_cell(result),
                key=result.url,
            )
        else:
            # Bestehende Zeile in-place aktualisieren
            table = self.query_one("#url-data", DataTable)
            self._update_row_cells(table, result)

        if self._auto_scroll:
            try:
                idx = self._filtered.index(result)
                if idx >= self._auto_scroll_row:
                    self._auto_scroll_row = idx
            except ValueError:
                pass
            table = self.query_one("#url-data", DataTable)
            table.move_cursor(row=self._auto_scroll_row)

        self._update_count_label()

    def _scroll_to_result(self, result: CrawlResult) -> None:
        """Merkt sich die Ziel-Zeile fuer Auto-Scroll.

        Bei mehreren parallelen Crawl-Threads wird nur vorwaerts gescrollt,
        damit der Cursor nicht zwischen aktiven Threads hin- und herspringt.

        Args:
            result: Das CrawlResult zu dem gescrollt werden soll.
        """
        try:
            row = self._filtered.index(result)
            if row >= self._auto_scroll_row:
                self._auto_scroll_row = row
        except ValueError:
            pass

    def toggle_error_filter(self) -> bool:
        """Schaltet den Error-Filter um.

        Returns:
            True wenn der Filter jetzt aktiv ist.
        """
        self._show_only_errors = not self._show_only_errors
        self._apply_filter()
        return self._show_only_errors

    def on_key(self, event) -> None:
        """Deaktiviert Auto-Scroll bei manueller Navigation.

        Args:
            event: Das Key-Event.
        """
        if event.key in self._NAV_KEYS:
            self._auto_scroll = False

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Sendet ein UrlHighlighted-Event bei Cursor-Bewegung."""
        if event.row_key and event.row_key.value:
            url = event.row_key.value
            for result in self._filtered:
                if result.url == url:
                    self.post_message(self.UrlHighlighted(result))
                    break
