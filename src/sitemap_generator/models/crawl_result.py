"""Datenmodelle fuer den Crawl-Vorgang."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


def friendly_error_message(error: Exception) -> str:
    """Wandelt technische Netzwerkfehler in benutzerfreundliche Meldungen um.

    Args:
        error: Die aufgetretene Exception.

    Returns:
        Verstaendliche Fehlermeldung auf Deutsch.
    """
    msg = str(error).lower()

    if "getaddrinfo failed" in msg or "name or service not known" in msg:
        return "DNS-Fehler: Domain konnte nicht aufgeloest werden (Tippfehler in der URL?)"
    if "no address associated" in msg:
        return "DNS-Fehler: Keine IP-Adresse fuer diese Domain gefunden"
    if "connection refused" in msg or "errno 111" in msg:
        return "Verbindung abgelehnt: Server antwortet nicht auf diesem Port"
    if "connection reset" in msg or "errno 104" in msg:
        return "Verbindung vom Server zurueckgesetzt"
    if "timed out" in msg or "timeout" in msg:
        return "Timeout: Server hat nicht rechtzeitig geantwortet"
    if "ssl" in msg or "certificate" in msg:
        return f"SSL/TLS-Fehler: {error}"
    if "too many redirects" in msg or "toomanyredirects" in msg:
        return "Zu viele Weiterleitungen (Redirect-Schleife?)"

    return str(error)


class PageStatus(Enum):
    """Status einer gecrawlten Seite."""
    PENDING = "pending"
    CRAWLING = "crawling"
    OK = "ok"
    REDIRECT = "redirect"
    REDIRECT_EXTERNAL = "redirect_external"  # Redirect auf andere Domain
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"      # robots.txt disallowed or filtered
    MAX_DEPTH = "max_depth"  # max depth reached


@dataclass
class CrawlResult:
    """Ergebnis fuer eine einzelne gecrawlte URL."""
    url: str
    status: PageStatus = PageStatus.PENDING
    http_status_code: int = 0
    content_type: str = ""
    depth: int = 0
    parent_url: str = ""
    load_time_ms: float = 0
    last_modified: str = ""        # from HTTP Last-Modified header
    links_found: int = 0           # number of internal links found on page
    error_message: str = ""
    redirect_url: str = ""             # final URL after redirect(s)
    referring_pages: list[dict] = field(default_factory=list)
    # ^ [{"url": "https://...", "link_text": "Mehr erfahren"}]

    @property
    def is_error(self) -> bool:
        """True wenn HTTP-Fehler (4xx/5xx) oder Status ERROR/TIMEOUT.

        Redirects (intern und extern) sind KEINE Fehler.
        """
        if self.status in (PageStatus.REDIRECT, PageStatus.REDIRECT_EXTERNAL):
            return False
        return (
            self.http_status_code >= 400
            or self.status in (PageStatus.ERROR, PageStatus.TIMEOUT)
        )

    @property
    def is_external_redirect(self) -> bool:
        """True wenn die Seite auf eine externe Domain redirected."""
        return self.status == PageStatus.REDIRECT_EXTERNAL

    @property
    def status_icon(self) -> str:
        """Emoji-Icon fuer den Status (Baum, Detail-Panel)."""
        icons = {
            PageStatus.PENDING: "⏳",
            PageStatus.CRAWLING: "🔄",
            PageStatus.OK: "✅",
            PageStatus.REDIRECT: "↪️",
            PageStatus.REDIRECT_EXTERNAL: "↗️",
            PageStatus.ERROR: "❌",
            PageStatus.TIMEOUT: "⏱️",
            PageStatus.SKIPPED: "🚫",
            PageStatus.MAX_DEPTH: "📏",
        }
        return icons.get(self.status, "?")

    @property
    def status_label(self) -> tuple[str, str]:
        """Kurzes Text-Label mit Farbe fuer die Tabelle.

        Returns:
            Tuple (label, rich_style) z.B. ("ERR", "bold red").
        """
        labels: dict[PageStatus, tuple[str, str]] = {
            PageStatus.PENDING: ("...", "dim"),
            PageStatus.CRAWLING: (">>>", "bold cyan"),
            PageStatus.OK: ("OK", "green"),
            PageStatus.REDIRECT: ("→", "cyan"),
            PageStatus.REDIRECT_EXTERNAL: ("→", "dim"),
            PageStatus.ERROR: ("ERR", "bold red"),
            PageStatus.TIMEOUT: ("TO", "bold red"),
            PageStatus.SKIPPED: ("IGN", "yellow"),
            PageStatus.MAX_DEPTH: ("MAX", "dim"),
        }
        return labels.get(self.status, ("?", ""))

    @property
    def is_successful(self) -> bool:
        return self.status in (
            PageStatus.OK, PageStatus.REDIRECT, PageStatus.REDIRECT_EXTERNAL,
        )


@dataclass
class CrawlStats:
    """Statistiken des gesamten Crawl-Vorgangs."""
    total_discovered: int = 0
    total_crawled: int = 0
    total_errors: int = 0
    total_skipped: int = 0
    total_2xx: int = 0
    total_3xx: int = 0
    total_4xx: int = 0
    total_5xx: int = 0
    queue_size: int = 0
    max_depth_reached: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None
    urls_per_second: float = 0

    @property
    def duration_seconds(self) -> float:
        if not self.start_time:
            return 0
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def duration_display(self) -> str:
        secs = self.duration_seconds
        if secs < 60:
            return f"{secs:.0f}s"
        mins = int(secs // 60)
        remaining = int(secs % 60)
        if mins < 60:
            return f"{mins}m {remaining}s"
        hours = mins // 60
        remaining_mins = mins % 60
        return f"{hours}h {remaining_mins}m"
