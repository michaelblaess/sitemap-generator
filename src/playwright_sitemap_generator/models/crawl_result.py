"""Datenmodelle fuer den Crawl-Vorgang."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class PageStatus(Enum):
    """Status einer gecrawlten Seite."""
    PENDING = "pending"
    CRAWLING = "crawling"
    OK = "ok"
    REDIRECT = "redirect"
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

    @property
    def status_icon(self) -> str:
        icons = {
            PageStatus.PENDING: "⏳",
            PageStatus.CRAWLING: "🔄",
            PageStatus.OK: "✅",
            PageStatus.REDIRECT: "↪️",
            PageStatus.ERROR: "❌",
            PageStatus.TIMEOUT: "⏱️",
            PageStatus.SKIPPED: "🚫",
            PageStatus.MAX_DEPTH: "📏",
        }
        return icons.get(self.status, "?")

    @property
    def is_successful(self) -> bool:
        return self.status in (PageStatus.OK, PageStatus.REDIRECT)


@dataclass
class CrawlStats:
    """Statistiken des gesamten Crawl-Vorgangs."""
    total_discovered: int = 0
    total_crawled: int = 0
    total_errors: int = 0
    total_skipped: int = 0
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
