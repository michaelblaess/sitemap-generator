"""URL-Tabelle Widget - Zeigt gecrawlte URLs mit Status und Farbcodierung an."""

from __future__ import annotations

import contextlib

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import DataTable, Input, Static, TabbedContent, TabPane
from textual_widgets import SearchInputWithHistory

from ..i18n import t
from ..models.crawl_result import CrawlResult, PageStatus
from .page_tree import PageTree

# Spinner-Frames fuer CRAWLING-Status
SPINNER_FRAMES = [">  ", ">> ", ">>>", " >>", "  >", "   "]


class UrlTable(Static):
    """Tabelle aller entdeckten URLs mit Live-Status-Updates und Farbcodierung."""

    DEFAULT_CSS = """
    UrlTable #results-count {
        display: none;
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }

    UrlTable #filter-search {
        height: auto;
    }

    UrlTable TabbedContent {
        height: 1fr;
    }

    UrlTable TabPane {
        padding: 0;
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
        self._known_urls: set[str] = set()
        self._auto_scroll: bool = True
        self._auto_scroll_row: int = -1

    def compose(self) -> ComposeResult:
        """Erstellt Filter + Tabs (Ergebnisse / Baumansicht)."""
        yield Static("", id="results-count")
        yield SearchInputWithHistory(
            placeholder=t("table.filter_placeholder"),
            icon="🔍",
            input_id="filter-bar",
            dropdown_id="filter-dropdown",
            id="filter-search",
        )
        with TabbedContent(id="url-tabs"):
            with TabPane(t("table.tab_results"), id="tab-results"):
                yield DataTable(id="url-data", cursor_type="row")
            with TabPane(t("table.tab_tree"), id="tab-tree"):
                yield PageTree(id="page-tree")

    def on_mount(self) -> None:
        """Initialisiert die Tabellenspalten und startet den Spinner-Timer."""
        table = self.query_one("#url-data", DataTable)
        self._col_keys = table.add_columns(
            t("table.columns.number"),
            t("table.columns.status"),
            t("table.columns.http"),
            t("table.columns.depth"),
            t("table.columns.links"),
            t("table.columns.form"),
            t("table.columns.time"),
            t("table.columns.url"),
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
            # Filter wirkt auch auf den Baum-Tab
            with contextlib.suppress(Exception):
                self.query_one("#page-tree", PageTree).apply_filter(self._filter_text)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Uebernimmt den Filter-Begriff in die Verlaufs-Historie (Enter)."""
        if event.input.id == "filter-bar" and event.value.strip():
            self.query_one("#filter-search", SearchInputWithHistory).add(event.value.strip())

    def _tick_spinner(self) -> None:
        """Aktualisiert den Spinner-Frame der CRAWLING-Zeilen in-place."""
        has_crawling = any(r.status == PageStatus.CRAWLING for r in self._filtered)
        if not has_crawling:
            return
        self._spinner_frame = (self._spinner_frame + 1) % len(SPINNER_FRAMES)
        table = self.query_one("#url-data", DataTable)
        for _idx, result in enumerate(self._filtered):
            if result.status == PageStatus.CRAWLING:
                table.update_cell(
                    result.url,
                    self._col_keys[1],
                    self._status_cell(result),
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
        if self._sitemap_urls and result.http_status_code == 200 and result.url not in self._sitemap_urls:
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

    def _is_redirect_to_known_url(self, result: CrawlResult) -> bool:
        """Interner Redirect, dessen Ziel bereits in den Ergebnissen vorhanden ist.

        Typisches Beispiel: ``/kontakt`` -> 301 -> ``/kontakt/`` und ``/kontakt/``
        ist sowieso schon gecrawlt. Diese Doppel-Eintraege blenden wir in der
        Tabelle und im Baum aus, behalten sie aber in ``self._results`` —
        spaeter wertvoll fuer den "interne Links bereinigen"-Bericht.
        """
        if result.status != PageStatus.REDIRECT:
            return False
        target = (result.redirect_url or "").split("#", 1)[0]
        if not target or target == result.url:
            return False
        return target in self._known_urls

    def _matches_filter(self, result: CrawlResult) -> bool:
        """Prueft ob ein Ergebnis dem aktuellen Filter entspricht.

        Args:
            result: Das zu pruefende CrawlResult.

        Returns:
            True wenn das Ergebnis angezeigt werden soll.
        """
        if self._show_only_errors and not result.is_error:
            return False
        # Interne Redirects, deren Ziel sowieso schon in der Tabelle steht,
        # ausblenden — sonst landet z.B. /kontakt (301) und /kontakt/ (200)
        # als zwei nahezu identische Zeilen in der Liste.
        if self._is_redirect_to_known_url(result):
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
        table.update_cell(
            row_key, self._col_keys[6], f"{result.load_time_ms / 1000:.1f}s" if result.load_time_ms else "-"
        )
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
        # Leeres Zaehler-Label nicht anzeigen (sonst Leerzeile ueber dem Filter)
        if total == 0:
            count_label.display = False
            return
        count_label.display = True
        if total == shown:
            key = "table.count_one" if total == 1 else "table.count"
            count_label.update(t(key, count=total))
        else:
            count_label.update(t("table.count_filtered", shown=shown, total=total))

    def clear_results(self) -> None:
        """Leert alle Ergebnisse, die Tabelle und den Baum-Tab."""
        self._results.clear()
        self._filtered.clear()
        self._known_urls.clear()
        self._row_counter = 0
        self._filter_text = ""
        self._auto_scroll = True
        self._auto_scroll_row = -1
        table = self.query_one("#url-data", DataTable)
        table.clear()
        with contextlib.suppress(Exception):
            self.query_one("#page-tree", PageTree).clear()
        self._update_count_label()

    def rebuild_tree(self, start_url: str) -> None:
        """Aktualisiert den Baum-Tab aus den aktuell geladenen Ergebnissen.

        Wird typisch am Crawl-Ende aufgerufen (waehrend des Crawls bleibt der
        Baum still — die DataTable updated live, der Baum kommt am Ende dazu).

        Args:
            start_url:
                Start-URL des Crawls (Wurzel des Baums).
        """
        try:
            tree = self.query_one("#page-tree", PageTree)
        except Exception:
            return
        tree.set_data(self._results, start_url, self._sitemap_urls)
        if self._filter_text:
            tree.apply_filter(self._filter_text)

    def load_results(self, results: list[CrawlResult]) -> None:
        """Laedt alle Ergebnisse in die Tabelle.

        Setzt Auto-Scroll zurueck, damit beim naechsten Crawl
        automatisch zur aktuellen Zeile gescrollt wird.

        Args:
            results: Liste der CrawlResults.
        """
        self._results = results
        self._known_urls = {r.url for r in results}
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
            self._known_urls.add(result.url)
            # Wenn dieses neue Ergebnis Ziel eines bereits angezeigten 3xx-
            # Redirects ist, muss die Tabelle neu gefiltert werden, damit
            # der Duplikat-Eintrag verschwindet.
            if result.status != PageStatus.REDIRECT and any(
                r.status == PageStatus.REDIRECT and (r.redirect_url or "").split("#", 1)[0] == result.url
                for r in self._filtered
            ):
                self._filtered = [r for r in self._results if self._matches_filter(r)]
                self._refresh_table()
                return

        if self._show_only_errors or self._filter_text:
            # Filter aktiv - Struktur koennte sich aendern
            self._filtered = [r for r in self._results if self._matches_filter(r)]
            if self._auto_scroll:
                self._scroll_to_result(result)
            self._refresh_table()
            return

        # Kein Filter aktiv
        if is_new:
            # Redirects, deren Ziel sowieso schon in der Tabelle steht,
            # nicht als Zeile zeigen (bleiben in _results fuer Reports).
            if self._is_redirect_to_known_url(result):
                return
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

    def on_key(self, event: events.Key) -> None:
        """Esc verlaesst das Filterfeld; Nav-Tasten deaktivieren Auto-Scroll.

        Esc im Filterfeld gibt den Fokus zurueck an die Tabelle (Footer kommt
        zurueck). Der Fokuswechsel wird via call_after_refresh verzoegert, sonst
        wird er im selben Event-Zyklus wieder ueberschrieben.

        Args:
            event: Das Key-Event.
        """
        if event.key == "escape":
            focused = self.app.focused
            if isinstance(focused, Input) and focused.id == "filter-bar":
                event.stop()
                table = self.query_one("#url-data", DataTable)
                self.call_after_refresh(lambda: self.app.set_focus(table))
            return
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
