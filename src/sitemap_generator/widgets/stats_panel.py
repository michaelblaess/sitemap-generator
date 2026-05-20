"""Statistik-Panel Widget - Zeigt die URL-Detailansicht an."""

from __future__ import annotations

from urllib.parse import quote, urlparse, urlunparse

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ..i18n import t
from ..models.crawl_result import CrawlResult, SeoInfo
from ..services.page_analysis import detect_issues


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
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            safe_path,
            parsed.params,
            safe_query,
            parsed.fragment,
        )
    )


def _format_load_time(ms: float) -> str:
    """Formatiert eine Ladezeit (de-DE).

    Ab einer Sekunde als Sekundenwert mit einer Nachkommastelle
    (z.B. "1,8s"), darunter in Millisekunden (z.B. "839ms").

    Args:
        ms: Ladezeit in Millisekunden.

    Returns:
        Formatierte Ladezeit, "-" wenn keine Zeit vorliegt.
    """
    if ms <= 0:
        return "-"
    if ms >= 1000:
        return f"{ms / 1000:.1f}".replace(".", ",") + "s"
    return f"{ms:.0f}ms"


def _format_size(num_bytes: int) -> str:
    """Formatiert eine Byte-Groesse als B / KB / MB (de-DE).

    Args:
        num_bytes: Groesse in Bytes.

    Returns:
        Formatierte Groesse, "-" wenn keine Groesse vorliegt.
    """
    if num_bytes <= 0:
        return "-"
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f}".replace(".", ",") + " KB"
    return f"{num_bytes / (1024 * 1024):.1f}".replace(".", ",") + " MB"


class StatsPanel(VerticalScroll):
    """Panel mit URL-Detail-Ansicht (scrollbar bei langem Inhalt)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._selected_result: CrawlResult | None = None

    def compose(self) -> ComposeResult:
        """Erstellt das Panel-Layout."""
        yield Static("", id="url-detail")

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

    @staticmethod
    def _panel(title: str, body: list, border_style: str = "grey37") -> Panel:
        """Baut ein bordiertes Panel mit linksbuendigem Titel.

        Args:
            title: Der Panel-Titel.
            body: Die Renderables im Panel.
            border_style: Rich-Style fuer den Rahmen.

        Returns:
            Das fertige Panel.
        """
        return Panel(
            Group(*body),
            title=f" {title} ",
            title_align="left",
            border_style=border_style,
            padding=(0, 1),
        )

    def _seo_lines(self, seo: SeoInfo) -> list[Text]:
        """Baut die SEO-Detailzeilen.

        Args:
            seo:
                Die SEO-Daten der Seite.

        Returns:
            Liste der Detailzeilen, leer wenn keine SEO-Daten vorliegen.
        """
        if not (seo.title or seo.description or seo.h1_count):
            return []
        title = f"{seo.title}  ({len(seo.title)})" if seo.title else "-"
        description = f"{seo.description}  ({len(seo.description)})" if seo.description else "-"
        viewport = t("detail.form_yes") if seo.has_viewport else t("detail.form_no")
        lines = [
            self._detail_line(t("detail.seo_title"), title),
            self._detail_line(t("detail.seo_desc"), description),
            self._detail_line(t("detail.seo_h1"), str(seo.h1_count)),
            self._detail_line(t("detail.seo_lang"), seo.lang or "-"),
            self._detail_line(t("detail.seo_canonical"), _sanitize_url(seo.canonical) if seo.canonical else "-"),
            self._detail_line(t("detail.seo_viewport"), viewport),
        ]
        if seo.robots:
            lines.append(self._detail_line(t("detail.seo_robots"), seo.robots))
        if seo.og_tags:
            lines.append(self._detail_line(t("detail.seo_og"), ", ".join(seo.og_tags)))
        return lines

    def _page_panel(self, result: CrawlResult) -> Panel:
        """Baut das Panel mit den Basis-Infos der Seite."""
        safe_url = _sanitize_url(result.url)
        lines = [
            self._detail_line(t("detail.url"), safe_url, "bold", link_url=safe_url),
            self._detail_line(t("detail.status"), f"{result.status_icon} {result.status.value}"),
        ]
        if result.redirect_url:
            safe_redirect = _sanitize_url(result.redirect_url)
            lines.append(self._detail_line(t("detail.redirect"), safe_redirect, link_url=safe_redirect))
        lines.append(
            self._detail_line(t("detail.http"), str(result.http_status_code) if result.http_status_code else "-")
        )
        lines.append(self._detail_line(t("detail.depth"), str(result.depth)))
        lines.append(self._detail_line(t("detail.links"), str(result.links_found)))
        lines.append(self._detail_line(t("detail.load_time"), _format_load_time(result.load_time_ms)))
        lines.append(self._detail_line(t("detail.size"), _format_size(result.page_size)))
        form_value = t("detail.form_yes") if result.has_form else t("detail.form_no")
        lines.append(self._detail_line(t("detail.form"), form_value, "green" if result.has_form else "dim"))
        if result.content_type:
            lines.append(self._detail_line(t("detail.content_type"), result.content_type))
        if result.last_modified:
            lines.append(self._detail_line(t("detail.last_modified"), result.last_modified))
        if result.parent_url:
            safe_parent = _sanitize_url(result.parent_url)
            lines.append(self._detail_line(t("detail.parent"), safe_parent, link_url=safe_parent))
        # Tech-Stack inline mitnehmen — eine knappe Zeile, dafuer kein
        # eigenes 1-Zeilen-Panel.
        if result.tech:
            lines.append(self._detail_line(t("detail.tech"), ", ".join(result.tech)))
        if result.error_message:
            lines.append(self._detail_line(t("detail.error"), result.error_message, "red"))
        return self._panel(t("detail.page_heading"), lines)

    def _issues_panel(self, result: CrawlResult) -> Panel | None:
        """Panel mit erkannten Problemen — None wenn keine, dann wird nichts gezeigt."""
        issues = detect_issues(result)
        if not issues:
            return None
        body: list = [Text(f"  • {issue}", style="yellow") for issue in issues]
        return self._panel(t("detail.issues_heading"), body, border_style="red")

    def _referring_panel(self, result: CrawlResult) -> Panel:
        """Baut das Panel mit den verweisenden Seiten (fuer 4xx/5xx)."""
        ref_lines: list = []
        for ref in result.referring_pages:
            link_text = ref.get("link_text", "").strip() or "Link"
            ref_url = _sanitize_url(ref.get("url", ""))
            ref_line = Text(overflow="fold")
            ref_line.append(f'  "{link_text}" → ')
            ref_line.append(ref_url, style=f"link {ref_url}")
            ref_lines.append(ref_line)
        return self._panel(t("detail.referring_pages"), ref_lines)

    def show_url_detail(self, result: CrawlResult) -> None:
        """Zeigt Detail-Infos zur markierten URL.

        Jeder thematische Block (Seite, Probleme, Tech-Stack, SEO,
        HTTP-Header, verweisende Seiten) ist ein eigenes bordiertes Panel.

        Args:
            result: Das CrawlResult der markierten URL.
        """
        self._selected_result = result

        # Reihenfolge: Seite (Tech inline) > Probleme (nur wenn vorhanden)
        # > HTTP-Header > SEO/Meta > Verweisende Seiten.
        panels: list = [self._page_panel(result)]

        issues_panel = self._issues_panel(result)
        if issues_panel is not None:
            panels.append(issues_panel)

        if result.response_headers:
            http_lines = [self._detail_line(name, value) for name, value in result.response_headers.items()]
            panels.append(self._panel(t("detail.http_heading"), http_lines))

        seo_lines = self._seo_lines(result.seo)
        if seo_lines:
            panels.append(self._panel(t("detail.seo_heading"), seo_lines))

        # Verweisende Seiten nur fuer 4xx/5xx Fehler anzeigen
        if result.referring_pages and result.http_status_code >= 400:
            panels.append(self._referring_panel(result))

        panels.append(Text(t("detail.ctrl_click"), style="dim italic"))

        detail = self.query_one("#url-detail", Static)
        detail.update(Group(*panels))

    def clear_detail(self) -> None:
        """Setzt das URL-Detail-Panel zurueck."""
        self._selected_result = None
        detail = self.query_one("#url-detail", Static)
        detail.update("")
