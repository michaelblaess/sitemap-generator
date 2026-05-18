"""History-Screen fuer den Sitemap Generator.

Zeigt eine Liste vergangener Crawls und ermoeglicht die Wiederholung
eines ausgewaehlten Crawls.
"""

from __future__ import annotations

from urllib.parse import urlparse

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

from ..i18n import t
from ..models.history import History, HistoryEntry


class HistoryScreen(ModalScreen[HistoryEntry | None]):
    """Modal-Dialog zur Anzeige und Auswahl vergangener Crawls.

    Gibt den ausgewaehlten HistoryEntry per dismiss() zurueck
    oder None wenn der Dialog ohne Auswahl geschlossen wird.
    """

    DEFAULT_CSS = """
    HistoryScreen {
        align: center middle;
    }

    HistoryScreen > Vertical {
        width: 110;
        height: 35;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }

    HistoryScreen #history-title {
        height: 3;
        content-align: center middle;
        text-style: bold;
        background: $accent;
        color: auto;
        margin-bottom: 1;
    }

    HistoryScreen #history-empty {
        height: auto;
        padding: 2 4;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }

    HistoryScreen #history-table {
        height: 1fr;
    }

    HistoryScreen #history-buttons {
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    HistoryScreen #history-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entries: list[HistoryEntry] = []

    def compose(self) -> ComposeResult:
        """Erstellt das Modal-Layout."""
        self._entries = History.load()

        with Vertical():
            yield Static(t("history.title"), id="history-title")

            if not self._entries:
                yield Static(
                    t("history.empty"),
                    id="history-empty",
                )
            else:
                table: DataTable[str] = DataTable(id="history-table", cursor_type="row")
                table.add_columns(
                    t("history.col_number"),
                    t("history.col_date"),
                    t("history.col_url"),
                    t("history.col_params"),
                )
                for idx, entry in enumerate(self._entries, start=1):
                    # Datum kuerzen
                    date_str = entry.timestamp[:16].replace("T", " ") if entry.timestamp else "?"

                    # Hostname extrahieren
                    try:
                        host = urlparse(entry.url).hostname or entry.url
                    except Exception:
                        host = entry.url

                    # Parameter kompakt zusammenbauen
                    params = []
                    if entry.render:
                        params.append("--render")
                    if not entry.respect_robots:
                        params.append("--ignore-robots")
                    if entry.concurrency != 8:
                        params.append(f"-c {entry.concurrency}")
                    if entry.timeout != 30:
                        params.append(f"-t {entry.timeout}")
                    if entry.max_depth != 10:
                        params.append(f"-d {entry.max_depth}")
                    if entry.cookies:
                        cookie_names = ", ".join(c.get("name", "?") for c in entry.cookies)
                        params.append(f"--cookie {cookie_names}")
                    if entry.user_agent:
                        params.append("--user-agent ...")
                    param_str = "  ".join(params) if params else "-"

                    table.add_row(str(idx), date_str, host, param_str, key=str(idx))

                yield table

            with Horizontal(id="history-buttons"):
                if self._entries:
                    yield Button(t("history.btn_select"), variant="primary", id="history-select")
                yield Button(t("history.btn_close"), variant="default", id="history-close")

    def on_mount(self) -> None:
        """Fokussiert die Tabelle nach dem Oeffnen."""
        if self._entries:
            try:
                table = self.query_one("#history-table", DataTable)
                table.focus()
            except Exception:
                pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Verarbeitet die Auswahl einer Zeile per Enter oder Klick.

        Args:
            event: Das RowSelected-Event mit dem Key der Zeile.
        """
        try:
            idx = int(str(event.row_key.value)) - 1
            if 0 <= idx < len(self._entries):
                self.dismiss(self._entries[idx])
        except (ValueError, IndexError):
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Verarbeitet Klicks auf die Auswahl-/Schliessen-Buttons.

        Args:
            event: Das Pressed-Event mit dem geklickten Button.
        """
        if event.button.id == "history-select":
            self._select_highlighted()
        else:
            self.dismiss(None)

    def _select_highlighted(self) -> None:
        """Waehlt die aktuell in der Tabelle markierte Zeile aus."""
        try:
            table = self.query_one("#history-table", DataTable)
            idx = table.cursor_row
            if 0 <= idx < len(self._entries):
                self.dismiss(self._entries[idx])
        except Exception:
            pass

    def action_close(self) -> None:
        """Schliesst den Dialog ohne Auswahl."""
        self.dismiss(None)
