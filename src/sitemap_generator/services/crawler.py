"""Crawl-Engine - Durchsucht Websites rekursiv nach internen Links."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime
from typing import Callable
from urllib.parse import unquote, urljoin, urlparse, urlunparse, urldefrag, quote

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page

from ..models.crawl_result import CrawlResult, CrawlStats, PageStatus, friendly_error_message
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
        max_retries: int = 2,
    ) -> None:
        self.start_url = self._normalize_url(start_url)
        self.max_depth = max_depth
        self.concurrency = concurrency
        self.timeout = timeout
        self.render = render
        self.headless = headless
        self.respect_robots = respect_robots
        self.cookies = cookies or []
        self.max_retries = max_retries
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

        # Interner State
        self._results: dict[str, CrawlResult] = {}
        self._queue: deque[tuple[str, int, str]] = deque()  # (url, depth, parent)
        self._seen: set[str] = set()
        self._seed_urls: list[str] = []  # Zusaetzliche URLs aus Sitemap
        self._pending_referrers: dict[str, list[dict]] = {}  # URL -> [{url, link_text}]
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

        # Seed-URLs aus offizieller Sitemap einreihen (Tiefe 1, als ob
        # von der Startseite verlinkt). _enqueue filtert Duplikate.
        if self._seed_urls:
            seed_added = 0
            for url in self._seed_urls:
                if self._enqueue(url, depth=1, parent=self.start_url):
                    seed_added += 1
            if seed_added:
                log(f"  {seed_added} Seed-URLs aus Sitemap in Queue")

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

    def add_seed_urls(self, urls: set[str]) -> int:
        """Registriert zusaetzliche Seed-URLs fuer den naechsten Crawl.

        Die URLs werden beim Start von crawl() nach der Start-URL
        in die Queue eingereiht. Wird verwendet um URLs aus der offiziellen
        Sitemap einzuspeisen, die durch normales Crawling evtl. nicht
        erreichbar sind.

        Args:
            urls: Set von URLs die gecrawlt werden sollen.

        Returns:
            Anzahl der akzeptierten URLs (gleiche Domain).
        """
        accepted = 0
        for url in urls:
            parsed = urlparse(url)
            if parsed.netloc.lower() != self._allowed_domain:
                continue
            self._seed_urls.append(url)
            accepted += 1
        return accepted

    def cancel(self) -> None:
        """Bricht den Crawl-Vorgang ab."""
        self._cancelled = True

    def _full_normalize(self, url: str) -> str:
        """Normalisiert eine URL vollstaendig inkl. Scheme-Anpassung.

        Kombiniert _normalize_url (Encoding, Domain) mit Scheme-Normalisierung
        (http → https wenn Start-URL https ist).

        Args:
            url: Die zu normalisierende URL.

        Returns:
            Vollstaendig normalisierte URL.
        """
        normalized = self._normalize_url(url)
        parsed = urlparse(normalized)
        if parsed.scheme != self._scheme and parsed.netloc == self._allowed_domain:
            normalized = urlunparse((
                self._scheme, parsed.netloc, parsed.path,
                parsed.params, parsed.query, "",
            ))
        return normalized

    def _track_referring_page(self, target_url: str, source_url: str, link_text: str) -> None:
        """Fuegt eine verweisende Seite zum Ergebnis der Ziel-URL hinzu.

        Falls die Ziel-URL noch nicht gecrawlt wird, werden die Referrer
        zwischengespeichert und spaeter uebertragen.

        Args:
            target_url: Die Ziel-URL auf die verlinkt wird.
            source_url: Die Seite die den Link enthaelt.
            link_text: Der angezeigte Link-Text.
        """
        normalized = self._full_normalize(target_url)
        entry = {"url": source_url, "link_text": link_text}

        if normalized in self._results:
            referring = self._results[normalized].referring_pages
            # Duplikate vermeiden (gleiche Source-URL pro Ziel nur einmal)
            if any(r["url"] == source_url for r in referring):
                return
            # Max 50 referring_pages pro URL (Speicherbegrenzung)
            if len(referring) < 50:
                referring.append(entry)
        else:
            # Ziel-URL noch nicht in results - zwischenspeichern
            if normalized not in self._pending_referrers:
                self._pending_referrers[normalized] = []
            pending = self._pending_referrers[normalized]
            if not any(r["url"] == source_url for r in pending):
                if len(pending) < 50:
                    pending.append(entry)

    def _count_http_status(self, status_code: int) -> None:
        """Zaehlt den HTTP-Statuscode in die passende Kategorie.

        Args:
            status_code: HTTP-Statuscode.
        """
        category = status_code // 100
        if category == 2:
            self._stats.total_2xx += 1
        elif category == 3:
            self._stats.total_3xx += 1
        elif category == 4:
            self._stats.total_4xx += 1
            self._stats.total_errors += 1
        elif category == 5:
            self._stats.total_5xx += 1
            self._stats.total_errors += 1

    async def _crawl_url(
        self,
        url: str,
        depth: int,
        parent: str,
        semaphore: asyncio.Semaphore,
        on_result: Callable[[CrawlResult], None],
        log: Callable[[str], None],
    ) -> None:
        """Crawlt eine einzelne URL mit Retry-Logik.

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

        # Zwischengespeicherte Referrer uebertragen
        if url in self._pending_referrers:
            result.referring_pages.extend(self._pending_referrers.pop(url))

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
            last_error: Exception | None = None

            for attempt in range(self.max_retries + 1):
                try:
                    if self.render:
                        links_with_text = await self._fetch_with_playwright(url, result)
                    else:
                        links_with_text = await self._fetch_with_httpx(url, result)

                    result.load_time_ms = (time.monotonic() - start_time) * 1000
                    last_error = None
                    break

                except Exception as e:
                    last_error = e
                    if attempt < self.max_retries:
                        wait = 2 * (attempt + 1)
                        log(f"  [yellow]Retry {attempt + 1}/{self.max_retries}: {url}[/yellow]")
                        await asyncio.sleep(wait)

            if last_error is not None:
                result.status = PageStatus.ERROR
                friendly_msg = friendly_error_message(last_error)
                result.error_message = friendly_msg
                result.load_time_ms = (time.monotonic() - start_time) * 1000
                self._stats.total_errors += 1
                self._stats.total_crawled += 1
                log(f"  [red]ERR | {url} | {friendly_msg}[/red]")
                on_result(result)
                self._stats.queue_size = len(self._queue)
                return

            # Status bestimmen: Redirect vs. OK vs. Error
            if result.redirect_url:
                redirect_parsed = urlparse(result.redirect_url)
                if redirect_parsed.netloc.lower() != self._allowed_domain:
                    result.status = PageStatus.REDIRECT_EXTERNAL
                else:
                    result.status = PageStatus.REDIRECT
                self._stats.total_3xx += 1
            elif result.http_status_code >= 400:
                result.status = PageStatus.ERROR
                self._count_http_status(result.http_status_code)
            else:
                result.status = PageStatus.OK
                self._count_http_status(result.http_status_code)

            # Gefundene Links in Queue + referring_pages tracken
            new_links = 0
            for link_url, link_text in links_with_text:
                normalized = self._full_normalize(link_url)

                # Referring Page tracken (auch fuer noch nicht gecrawlte URLs)
                self._track_referring_page(link_url, url, link_text)

                if depth + 1 <= self.max_depth:
                    if self._enqueue(link_url, depth + 1, url):
                        new_links += 1
                else:
                    # Max-Depth erreicht - trotzdem zaehlen
                    if normalized not in self._seen:
                        self._seen.add(normalized)
                        max_result = CrawlResult(
                            url=normalized, depth=depth + 1,
                            parent_url=url, status=PageStatus.MAX_DEPTH,
                        )
                        self._results[normalized] = max_result
                        self._stats.total_discovered += 1

            result.links_found = len(links_with_text)

            self._stats.total_crawled += 1
            if depth > self._stats.max_depth_reached:
                self._stats.max_depth_reached = depth

            status_str = f"HTTP {result.http_status_code}" if result.http_status_code else "OK"
            time_str = f"{result.load_time_ms:.0f}ms"
            log(f"  {status_str} | {time_str} | d={depth} | +{new_links} Links | {url}")

            on_result(result)
            self._stats.queue_size = len(self._queue)

    async def _fetch_with_httpx(self, url: str, result: CrawlResult) -> list[tuple[str, str]]:
        """Laedt eine Seite mit httpx und extrahiert Links mit Text.

        Args:
            url: Die zu ladende URL.
            result: Das CrawlResult zum Befuellen.

        Returns:
            Liste von Tupeln (link_url, link_text).
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

        result.content_type = response.headers.get("content-type", "")
        result.last_modified = response.headers.get("last-modified", "")

        if response.history:
            # Redirect erkannt: Original-Statuscode speichern (301/302),
            # NICHT den finalen Code des Redirect-Ziels (der koennte 404 sein)
            result.http_status_code = response.history[0].status_code
            result.redirect_url = str(response.url)

            # Externe Redirects: keine Links extrahieren (andere Domain)
            redirect_parsed = urlparse(str(response.url))
            if redirect_parsed.netloc.lower() != self._allowed_domain:
                return []
        else:
            result.http_status_code = response.status_code

        # Nur HTML-Seiten nach Links durchsuchen
        if "text/html" not in result.content_type.lower():
            return []

        # Links extrahieren - bei internem Redirect den Pfad der finalen URL
        # verwenden (Trailing-Slash ist entscheidend fuer urljoin bei relativen
        # Links), aber die Original-Domain beibehalten (sonst schlaegt
        # _is_internal fehl bei Subdomain-Wechsel, z.B. www → non-www)
        if response.history:
            final_parsed = urlparse(str(response.url))
            orig_parsed = urlparse(url)
            base_url = urlunparse((
                orig_parsed.scheme, orig_parsed.netloc,
                final_parsed.path, "",
                final_parsed.query, "",
            ))
        else:
            base_url = url
        soup = BeautifulSoup(response.text, "lxml")
        result.has_form = bool(soup.find("form"))
        return self._extract_links(soup, base_url)

    async def _fetch_with_playwright(self, url: str, result: CrawlResult) -> list[tuple[str, str]]:
        """Laedt eine Seite mit Playwright und extrahiert Links mit Text aus dem DOM.

        Args:
            url: Die zu ladende URL.
            result: Das CrawlResult zum Befuellen.

        Returns:
            Liste von Tupeln (link_url, link_text).
        """
        page: Page | None = None
        try:
            page = await self._browser.new_page()

            # Response-Handler fuer HTTP-Status
            response = await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)

            if response:
                result.content_type = response.headers.get("content-type", "")
                result.last_modified = response.headers.get("last-modified", "")

                # Redirect-Erkennung via Playwright
                if response.request.redirected_from:
                    result.redirect_url = response.url
                    # Playwright liefert keinen intermediary Status-Code,
                    # daher 301 als Standard annehmen fuer Redirects
                    result.http_status_code = 301

                    # Externe Redirects: keine Links extrahieren
                    redirect_parsed = urlparse(response.url)
                    if redirect_parsed.netloc.lower() != self._allowed_domain:
                        return []
                else:
                    result.http_status_code = response.status

            # Form-Erkennung im gerenderten DOM
            result.has_form = await page.evaluate(
                "() => document.querySelectorAll('form').length > 0"
            )

            # Links mit Text aus dem gerenderten DOM extrahieren
            links_data = await page.evaluate(
                "() => {"
                "  return [...document.querySelectorAll('a[href]')]"
                "    .filter(a => a.href && a.href.startsWith('http'))"
                "    .map(a => ({"
                "      href: a.href,"
                "      text: (a.textContent || '').trim().substring(0, 200)"
                "    }));"
                "}"
            )

            return [
                (item["href"], item.get("text", ""))
                for item in links_data
                if self._is_internal(item["href"])
            ]

        finally:
            if page:
                await page.close()

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
        """Extrahiert interne Links mit Link-Text aus geparstem HTML.

        Args:
            soup: BeautifulSoup-Objekt der Seite.
            base_url: Basis-URL fuer relative Links.

        Returns:
            Liste von Tupeln (link_url, link_text).
        """
        links: list[tuple[str, str]] = []

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
                link_text = tag.get_text(strip=True)[:200]
                links.append((absolute, link_text))

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

        Normalisiert die URL vor dem Einfuegen (Scheme, Encoding, Domain).

        Args:
            url: Die URL.
            depth: Crawl-Tiefe.
            parent: Eltern-URL.

        Returns:
            True wenn die URL neu war und hinzugefuegt wurde.
        """
        normalized = self._full_normalize(url)

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
        """Normalisiert eine URL fuer Deduplizierung.

        Normalisierungsschritte:
        - Scheme und Domain lowercase
        - Percent-Encoding normalisieren (dekodieren und einheitlich
          re-enkodieren, damit z.B. gesch%C3%A4ftskunden und
          geschäftskunden als gleich erkannt werden)
        - Leerer Pfad wird zu /
        - Fragment entfernen

        Args:
            url: Die zu normalisierende URL.

        Returns:
            Normalisierte URL.
        """
        parsed = urlparse(url)

        # Scheme und Domain lowercase
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Pfad: Percent-Encoding normalisieren
        # (dekodieren und einheitlich re-enkodieren, damit %C3%A4 und ä
        # als identisch erkannt werden)
        path = unquote(parsed.path)
        path = quote(path, safe="/:@!$&'*+,;=-._~")
        if not path:
            path = "/"

        # Query ebenfalls normalisieren
        query = unquote(parsed.query)
        query = quote(query, safe="/:@!$&'*+,;=-._~?=")

        # Fragment entfernen
        normalized = urlunparse((scheme, netloc, path, parsed.params, query, ""))
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
