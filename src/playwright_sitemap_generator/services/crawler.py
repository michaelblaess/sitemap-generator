"""Crawl-Engine - Durchsucht Websites rekursiv nach internen Links."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime
from typing import Callable
from urllib.parse import urljoin, urlparse, urlunparse, urldefrag

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page

from ..models.crawl_result import CrawlResult, CrawlStats, PageStatus
from ..models.robots import RobotsChecker


# URL-Endungen die uebersprungen werden (keine HTML-Seiten)
SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".gz", ".tar", ".7z",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".css", ".js", ".json", ".xml", ".woff", ".woff2", ".ttf", ".eot",
    ".exe", ".dmg", ".apk", ".msi",
}


class Crawler:
    """Rekursiver Web-Crawler mit httpx und optionalem Playwright-Rendering.

    Crawlt eine Website ausgehend von einer Start-URL, folgt internen Links
    und sammelt alle gefundenen Seiten.
    """

    def __init__(
        self,
        start_url: str,
        max_depth: int = 10,
        concurrency: int = 8,
        timeout: int = 30,
        render: bool = False,
        headless: bool = True,
        respect_robots: bool = True,
        cookies: list[dict[str, str]] | None = None,
        user_agent: str = "",
    ) -> None:
        self.start_url = self._normalize_url(start_url)
        self.max_depth = max_depth
        self.concurrency = concurrency
        self.timeout = timeout
        self.render = render
        self.headless = headless
        self.respect_robots = respect_robots
        self.cookies = cookies or []
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

        # Interner State
        self._results: dict[str, CrawlResult] = {}
        self._queue: deque[tuple[str, int, str]] = deque()  # (url, depth, parent)
        self._seen: set[str] = set()
        self._robots = RobotsChecker()
        self._stats = CrawlStats()
        self._cancelled = False

        # Playwright
        self._playwright = None
        self._browser: Browser | None = None

        # Domain-Filter: nur gleiche Domain crawlen
        parsed = urlparse(self.start_url)
        self._allowed_domain = parsed.netloc.lower()
        self._scheme = parsed.scheme

    @property
    def results(self) -> list[CrawlResult]:
        """Alle Crawl-Ergebnisse als Liste."""
        return list(self._results.values())

    @property
    def stats(self) -> CrawlStats:
        """Aktuelle Crawl-Statistiken."""
        return self._stats

    async def crawl(
        self,
        on_result: Callable[[CrawlResult], None] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> list[CrawlResult]:
        """Startet den Crawl-Vorgang.

        Args:
            on_result: Callback fuer jedes gecrawlte Ergebnis.
            log: Callback fuer Log-Meldungen.

        Returns:
            Liste aller Crawl-Ergebnisse.
        """
        if log is None:
            log = lambda msg: None
        if on_result is None:
            on_result = lambda r: None

        self._stats.start_time = datetime.now()

        # robots.txt laden
        if self.respect_robots:
            log("Lade robots.txt...")
            await self._robots.load(self.start_url, cookies=self.cookies)
            if self._robots.sitemaps:
                log(f"  robots.txt: {len(self._robots.sitemaps)} Sitemap(s) gefunden")
            log("  robots.txt geladen")
        else:
            log("robots.txt wird ignoriert (--ignore-robots)")

        # Start-URL in Queue
        self._enqueue(self.start_url, depth=0, parent="")

        # Browser starten falls Render-Modus
        if self.render:
            log("Starte Playwright Browser...")
            self._playwright = await async_playwright().start()
            self._browser = await self._launch_browser()
            log("Browser gestartet")

        semaphore = asyncio.Semaphore(self.concurrency)
        active_tasks: set[asyncio.Task] = set()

        try:
            while (self._queue or active_tasks) and not self._cancelled:
                # Neue Tasks starten
                while self._queue and len(active_tasks) < self.concurrency:
                    url, depth, parent = self._queue.popleft()
                    self._stats.queue_size = len(self._queue)

                    task = asyncio.create_task(
                        self._crawl_url(url, depth, parent, semaphore, on_result, log)
                    )
                    active_tasks.add(task)
                    task.add_done_callback(active_tasks.discard)

                # Kurz warten wenn nichts in der Queue
                if not self._queue and active_tasks:
                    done, _ = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
                    for t in done:
                        active_tasks.discard(t)
                elif not active_tasks and not self._queue:
                    break
                else:
                    await asyncio.sleep(0.05)

        finally:
            # Auf verbleibende Tasks warten
            if active_tasks:
                await asyncio.gather(*active_tasks, return_exceptions=True)

            # Browser schliessen
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()

        self._stats.end_time = datetime.now()
        duration = self._stats.duration_seconds
        if duration > 0:
            self._stats.urls_per_second = self._stats.total_crawled / duration

        return self.results

    def cancel(self) -> None:
        """Bricht den Crawl-Vorgang ab."""
        self._cancelled = True

    async def _crawl_url(
        self,
        url: str,
        depth: int,
        parent: str,
        semaphore: asyncio.Semaphore,
        on_result: Callable[[CrawlResult], None],
        log: Callable[[str], None],
    ) -> None:
        """Crawlt eine einzelne URL.

        Args:
            url: Die zu crawlende URL.
            depth: Aktuelle Crawl-Tiefe.
            parent: URL der uebergeordneten Seite.
            semaphore: Concurrency-Begrenzung.
            on_result: Ergebnis-Callback.
            log: Log-Callback.
        """
        result = CrawlResult(url=url, depth=depth, parent_url=parent)
        self._results[url] = result

        # robots.txt Check
        if self.respect_robots and not self._robots.is_allowed(url):
            result.status = PageStatus.SKIPPED
            result.error_message = "robots.txt disallowed"
            self._stats.total_skipped += 1
            on_result(result)
            log(f"  [dim]SKIP (robots.txt): {url}[/dim]")
            return

        async with semaphore:
            if self._cancelled:
                return

            result.status = PageStatus.CRAWLING
            on_result(result)

            start_time = time.monotonic()

            try:
                if self.render:
                    links = await self._fetch_with_playwright(url, result)
                else:
                    links = await self._fetch_with_httpx(url, result)

                result.load_time_ms = (time.monotonic() - start_time) * 1000

                if result.status == PageStatus.CRAWLING:
                    result.status = PageStatus.OK

                # Gefundene Links in Queue
                new_links = 0
                for link in links:
                    if depth + 1 <= self.max_depth:
                        if self._enqueue(link, depth + 1, url):
                            new_links += 1
                    else:
                        # Max-Depth erreicht - trotzdem zaehlen
                        normalized = self._normalize_url(link)
                        if normalized not in self._seen:
                            self._seen.add(normalized)
                            max_result = CrawlResult(
                                url=normalized, depth=depth + 1,
                                parent_url=url, status=PageStatus.MAX_DEPTH,
                            )
                            self._results[normalized] = max_result
                            self._stats.total_discovered += 1

                result.links_found = len(links)

                self._stats.total_crawled += 1
                if depth > self._stats.max_depth_reached:
                    self._stats.max_depth_reached = depth

                status_str = f"HTTP {result.http_status_code}" if result.http_status_code else "OK"
                time_str = f"{result.load_time_ms:.0f}ms"
                log(f"  {status_str} | {time_str} | d={depth} | +{new_links} Links | {url}")

            except Exception as e:
                result.status = PageStatus.ERROR
                result.error_message = str(e)
                result.load_time_ms = (time.monotonic() - start_time) * 1000
                self._stats.total_errors += 1
                log(f"  [red]ERR | {url} | {e}[/red]")

            on_result(result)
            self._stats.queue_size = len(self._queue)

    async def _fetch_with_httpx(self, url: str, result: CrawlResult) -> list[str]:
        """Laedt eine Seite mit httpx und extrahiert Links.

        Args:
            url: Die zu ladende URL.
            result: Das CrawlResult zum Befuellen.

        Returns:
            Liste gefundener interner Links.
        """
        jar = httpx.Cookies()
        for c in self.cookies:
            jar.set(c["name"], c["value"])

        async with httpx.AsyncClient(
            timeout=float(self.timeout),
            follow_redirects=True,
            verify=False,
            cookies=jar,
            headers={"User-Agent": self.user_agent},
        ) as client:
            response = await client.get(url)

        result.http_status_code = response.status_code
        result.content_type = response.headers.get("content-type", "")
        result.last_modified = response.headers.get("last-modified", "")

        # Redirects erkennen
        if response.history:
            result.status = PageStatus.REDIRECT

        # Nur HTML-Seiten nach Links durchsuchen
        if "text/html" not in result.content_type.lower():
            return []

        # Links extrahieren mit BeautifulSoup
        soup = BeautifulSoup(response.text, "lxml")
        return self._extract_links(soup, url)

    async def _fetch_with_playwright(self, url: str, result: CrawlResult) -> list[str]:
        """Laedt eine Seite mit Playwright und extrahiert Links aus dem DOM.

        Args:
            url: Die zu ladende URL.
            result: Das CrawlResult zum Befuellen.

        Returns:
            Liste gefundener interner Links.
        """
        page: Page | None = None
        try:
            page = await self._browser.new_page()

            # Response-Handler fuer HTTP-Status
            response = await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)

            if response:
                result.http_status_code = response.status
                result.content_type = response.headers.get("content-type", "")
                result.last_modified = response.headers.get("last-modified", "")

                if response.request.redirected_from:
                    result.status = PageStatus.REDIRECT

            # Links aus dem gerenderten DOM extrahieren
            links = await page.evaluate(
                "() => {"
                "  return [...document.querySelectorAll('a[href]')]"
                "    .map(a => a.href)"
                "    .filter(href => href && href.startsWith('http'));"
                "}"
            )

            return [link for link in links if self._is_internal(link)]

        finally:
            if page:
                await page.close()

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Extrahiert interne Links aus geparstem HTML.

        Args:
            soup: BeautifulSoup-Objekt der Seite.
            base_url: Basis-URL fuer relative Links.

        Returns:
            Liste interner Link-URLs.
        """
        links: list[str] = []

        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()

            # Leere und spezielle Links ueberspringen
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
                continue

            # Relative URLs aufloesen
            absolute = urljoin(base_url, href)

            # Fragment entfernen
            absolute, _ = urldefrag(absolute)

            if self._is_internal(absolute):
                links.append(absolute)

        return links

    def _is_internal(self, url: str) -> bool:
        """Prueft ob eine URL zur gleichen Domain gehoert.

        Args:
            url: Die zu pruefende URL.

        Returns:
            True wenn die URL intern ist.
        """
        parsed = urlparse(url)
        return parsed.netloc.lower() == self._allowed_domain

    def _enqueue(self, url: str, depth: int, parent: str) -> bool:
        """Fuegt eine URL zur Crawl-Queue hinzu (wenn noch nicht gesehen).

        Args:
            url: Die URL.
            depth: Crawl-Tiefe.
            parent: Eltern-URL.

        Returns:
            True wenn die URL neu war und hinzugefuegt wurde.
        """
        normalized = self._normalize_url(url)

        # Bereits gesehen?
        if normalized in self._seen:
            return False

        # Datei-Endung pruefen
        path = urlparse(normalized).path.lower()
        for ext in SKIP_EXTENSIONS:
            if path.endswith(ext):
                return False

        self._seen.add(normalized)
        self._queue.append((normalized, depth, parent))
        self._stats.total_discovered += 1
        self._stats.queue_size = len(self._queue)
        return True

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalisiert eine URL (Trailing Slash, Lowercase Domain).

        Args:
            url: Die zu normalisierende URL.

        Returns:
            Normalisierte URL.
        """
        parsed = urlparse(url)

        # Scheme und Domain lowercase
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Pfad: Trailing Slash normalisieren
        path = parsed.path
        if not path:
            path = "/"

        # Query behalten, Fragment entfernen
        normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
        return normalized

    async def _launch_browser(self) -> Browser:
        """Startet den Browser (System-Chrome bevorzugt, Chromium als Fallback).

        Returns:
            Playwright Browser-Instanz.
        """
        launch_args = [
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ]

        # System-Chrome bevorzugen
        try:
            return await self._playwright.chromium.launch(
                channel="chrome",
                headless=self.headless,
                args=launch_args,
            )
        except Exception:
            pass

        # Fallback: gebundeltes Chromium
        return await self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args,
        )
