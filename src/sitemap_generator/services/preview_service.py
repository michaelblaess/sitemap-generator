"""Seiten-Vorschau: Screenshots per Playwright-Sidecar.

Eigenstaendige Playwright-Instanz nur fuer Screenshots - unabhaengig vom
gewaehlten Crawl-Modus (httpx oder Playwright). Der Browser wird lazy beim
ersten Screenshot gestartet und fuer weitere Aufrufe offen gehalten.
"""

from __future__ import annotations

import asyncio
import contextlib

from playwright.async_api import Browser, Playwright, async_playwright

# Viewport fuer die Screenshots (Above-the-fold-Ausschnitt).
_VIEWPORT = {"width": 1280, "height": 800}


class PreviewService:
    """Erzeugt Seiten-Screenshots ueber eine eigene Playwright-Instanz."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._cache: dict[str, bytes] = {}
        self._lock = asyncio.Lock()

    async def capture(self, url: str) -> bytes | None:
        """Liefert einen PNG-Screenshot der Seite.

        Bereits erstellte Screenshots werden zwischengespeichert.

        Args:
            url:
                Die zu fotografierende URL.

        Returns:
            PNG-Bilddaten oder None, wenn der Screenshot fehlschlaegt.
        """
        if url in self._cache:
            return self._cache[url]

        async with self._lock:
            if url in self._cache:
                return self._cache[url]
            try:
                browser = await self._ensure_browser()
                page = await browser.new_page(viewport=_VIEWPORT, ignore_https_errors=True)  # type: ignore[arg-type]
                try:
                    await page.goto(url, wait_until="load", timeout=15000)
                    data = await page.screenshot(type="png")
                finally:
                    await page.close()
            except Exception:
                return None

        self._cache[url] = data
        return data

    async def _ensure_browser(self) -> Browser:
        """Startet den Sidecar-Browser beim ersten Aufruf."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
            )
        return self._browser

    async def close(self) -> None:
        """Schliesst Browser und Playwright-Instanz best-effort.

        Beide Aufrufe einzeln gegen Exceptions abschirmen — sonst kann
        ein scheiternder Browser-Close das anschliessende
        ``playwright.stop()`` blockieren, das die OS-Pipe-Cleanup macht.
        """
        if self._browser is not None:
            with contextlib.suppress(Exception):
                await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            with contextlib.suppress(Exception):
                await self._playwright.stop()
            self._playwright = None
