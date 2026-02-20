"""Statistik-Panel Widget - Zeigt Crawl-Fortschritt und Statistiken an."""

from __future__ import annotations

from urllib.parse import quote, urlparse, urlunparse

from rich.console import Group
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from textual.app import ComposeResult
from textual.widgets import Static

from ..models.crawl_result import CrawlResult, CrawlStats, PageStatus


def _sanitize_url(url: str) -> str:
    """Bereinigt eine URL fuer Terminal-CTRL+Click-Kompatibilitaet.

    Kodiert Non-ASCII-Zeichen (Umlaute etc.) als Percent-Encoding,
    damit Terminals die URL beim CTRL+Click korrekt erkennen.
    Klammern werden ebenfalls kodiert.

    Args:
        url: Die zu bereinigende URL.

    Returns:
        Bereinigte URL mit Percent-Encoding fuer Non-ASCII-Zeichen.
    """
    parsed = urlparse(url)
    # Pfad und Query separat kodieren, bereits kodierte Zeichen beibehalten.
    # '%' muss safe sein, damit bereits kodierte Sequenzen (%C3%A4 etc.)
    # nicht doppelt kodiert werden (%25C3%25A4).
    safe_path = quote(parsed.path, safe="/:@!$&'*+,;=-._~%")
    safe_query = quote(parsed.query, safe="/:@!$&'*+,;=-._~?=%")
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        safe_path,
        parsed.params,
        safe_query,
        parsed.fragment,
    ))


class StatsPanel(Static):
    """Panel mit Live-Crawl-Statistiken und URL-Detail-Ansicht."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stats = CrawlStats()
        self._selected_result: CrawlResult | None = None

    def compose(self) -> ComposeResult:
        """Erstellt das Panel-Layout."""
        yield Static("Feuer frei - [bold]s[/bold] drücken, um den Scan zu starten", id="stats-content")
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
        table.add_row("2xx (OK)", f"[green]{stats.total_2xx}[/green]" if stats.total_2xx else "0")
        table.add_row("3xx (Redirect)", f"[yellow]{stats.total_3xx}[/yellow]" if stats.total_3xx else "0")
        table.add_row("4xx (Not Found)", f"[red]{stats.total_4xx}[/red]" if stats.total_4xx else "0")
        table.add_row("5xx (Server)", f"[red]{stats.total_5xx}[/red]" if stats.total_5xx else "0")
        table.add_row("Uebersprungen", str(stats.total_skipped))
        table.add_row("Queue", str(stats.queue_size))
        table.add_row("Max Tiefe", str(stats.max_depth_reached))
        table.add_row("Dauer", stats.duration_display)

        if stats.urls_per_second > 0:
            table.add_row("URLs/Sek", f"{stats.urls_per_second:.1f}")

        content = self.query_one("#stats-content", Static)
        content.update(table)

    @staticmethod
    def _detail_line(
        key: str,
        value: str,
        value_style: str = "",
        link_url: str = "",
    ) -> Text:
        """Erzeugt eine Key-Value-Zeile mit fixer Key-Breite und URL-Umbruch.

        Verwendet Text mit overflow=fold statt Table-Zellen,
        damit lange URLs korrekt umbrechen statt abgeschnitten zu werden.
        Bei link_url wird ein OSC 8 Terminal-Hyperlink erzeugt, sodass
        CTRL+Click die volle URL oeffnet - auch wenn der Text umbricht.

        Args:
            key: Beschriftung (links, dim).
            value: Wert (rechts).
            value_style: Optionaler Rich-Style fuer den Wert.
            link_url: Optionale URL fuer OSC 8 Hyperlink (CTRL+Click).

        Returns:
            Text-Objekt mit fold-overflow.
        """
        line = Text(overflow="fold")
        line.append(f" {key:<18} ", style="dim")
        # OSC 8 Hyperlink: Text kann umbrechen, CTRL+Click oeffnet trotzdem
        # die volle URL (im Terminal-Escape-Code eingebettet)
        style = value_style
        if link_url:
            style = f"{value_style} link {link_url}".strip()
        if style:
            line.append(value, style=style)
        else:
            line.append(value)
        return line

    def show_url_detail(self, result: CrawlResult) -> None:
        """Zeigt Detail-Infos zur markierten URL.

        Args:
            result: Das CrawlResult der markierten URL.
        """
        self._selected_result = result

        # Separator zwischen Stats und URL-Detail
        renderables: list = [Rule(style="dim")]

        # Einzelne Text-Zeilen statt Table: URLs werden korrekt umgebrochen.
        # link_url erzeugt OSC 8 Hyperlink → CTRL+Click oeffnet volle URL
        # auch wenn der angezeigte Text auf mehrere Zeilen umbricht.
        safe_url = _sanitize_url(result.url)
        renderables.append(self._detail_line(
            "URL", safe_url, "bold", link_url=safe_url,
        ))
        renderables.append(self._detail_line(
            "Status", f"{result.status_icon} {result.status.value}",
        ))
        if result.redirect_url:
            safe_redirect = _sanitize_url(result.redirect_url)
            renderables.append(self._detail_line(
                "Redirect", safe_redirect, link_url=safe_redirect,
            ))
        renderables.append(self._detail_line(
            "HTTP", str(result.http_status_code) if result.http_status_code else "-",
        ))
        renderables.append(self._detail_line("Crawl-Tiefe", str(result.depth)))
        renderables.append(self._detail_line("Links", str(result.links_found)))
        renderables.append(self._detail_line(
            "Ladezeit",
            f"{result.load_time_ms:.0f}ms" if result.load_time_ms else "-",
        ))
        form_value = "Ja" if result.has_form else "Nein"
        form_style = "green" if result.has_form else "dim"
        renderables.append(self._detail_line("Formular", form_value, form_style))

        if result.content_type:
            renderables.append(self._detail_line("Content-Type", result.content_type))
        if result.last_modified:
            renderables.append(self._detail_line("Last-Modified", result.last_modified))
        if result.parent_url:
            safe_parent = _sanitize_url(result.parent_url)
            renderables.append(self._detail_line(
                "Parent", safe_parent, link_url=safe_parent,
            ))
        if result.error_message:
            renderables.append(self._detail_line("Fehler", result.error_message, "red"))

        renderables.append(Text("CTRL+Klick auf URLs zum Oeffnen im Browser", style="dim italic"))

        # Verweisende Seiten nur fuer 4xx/5xx Fehler anzeigen
        if result.referring_pages and result.http_status_code >= 400:
            renderables.append(Rule(style="dim"))
            ref_lines = [Text("Verweisende Seiten:", style="bold")]
            for ref in result.referring_pages:
                link_text = ref.get("link_text", "").strip() or "Link"
                ref_url = _sanitize_url(ref.get("url", ""))
                ref_line = Text(overflow="fold")
                ref_line.append(f'  "{link_text}" \u2192 ')
                ref_line.append(ref_url, style=f"link {ref_url}")
                ref_lines.append(ref_line)
            renderables.extend(ref_lines)

        detail = self.query_one("#url-detail", Static)
        detail.update(Group(*renderables))

    def clear_detail(self) -> None:
        """Setzt das URL-Detail-Panel zurueck."""
        self._selected_result = None
        detail = self.query_one("#url-detail", Static)
        detail.update("")
