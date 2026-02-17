"""Sitemap-Autodiscovery und -Loader.

Findet die offizielle Sitemap einer Website automatisch und laedt alle
enthaltenen URLs. Wird verwendet um gecrawlte URLs mit der offiziellen
Sitemap abzugleichen.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Callable
from urllib.parse import urlparse, urlunparse

import httpx

from .crawl_result import friendly_error_message


# Standard-Namespace fuer Sitemaps
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Typische Sitemap-Pfade fuer Auto-Discovery (in Prioritaetsreihenfolge)
_COMMON_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap/sitemap.xml",
    "/sitemapindex.xml",
    "/sitemap/index.xml",
]


async def discover_sitemap(
    base_url: str,
    robots_sitemaps: list[str] | None = None,
    cookies: list[dict[str, str]] | None = None,
    log: Callable[[str], None] | None = None,
) -> str | None:
    """Findet die Sitemap-URL fuer eine Domain automatisch.

    Strategie:
    1. robots.txt Sitemap-Eintraege pruefen (bereits geladen vom Crawler)
    2. Typische Pfade durchprobieren (/sitemap.xml, ...)
    3. Erste gueltige URL zurueckgeben oder None

    Args:
        base_url: Basis-URL der Website.
        robots_sitemaps: Sitemap-URLs aus robots.txt (bereits geladen).
        cookies: Optionale Cookies.
        log: Optionale Log-Funktion.

    Returns:
        Die gefundene Sitemap-URL oder None.
    """
    if log is None:
        log = lambda msg: None

    parsed = urlparse(base_url)
    origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))

    jar = httpx.Cookies()
    for c in (cookies or []):
        jar.set(c["name"], c["value"])

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        verify=False,
        cookies=jar,
    ) as client:
        # Phase 1: robots.txt Sitemap-Eintraege (bereits vom Crawler geladen)
        if robots_sitemaps:
            for sitemap_url in robots_sitemaps:
                log(f"  Pruefe robots.txt Sitemap: {sitemap_url}")
                if await _is_valid_sitemap(client, sitemap_url):
                    log(f"  [green]Sitemap gefunden: {sitemap_url}[/green]")
                    return sitemap_url
                log(f"  {sitemap_url} nicht erreichbar, weiter...")

        # Phase 2: Typische Pfade durchprobieren
        log("  Probiere typische Sitemap-Pfade...")
        for path in _COMMON_SITEMAP_PATHS:
            candidate = f"{origin}{path}"
            log(f"  Teste: {candidate}")
            if await _is_valid_sitemap(client, candidate):
                log(f"  [green]Sitemap gefunden: {candidate}[/green]")
                return candidate

    log("  [yellow]Keine offizielle Sitemap gefunden[/yellow]")
    return None


async def load_sitemap_urls(
    sitemap_url: str,
    cookies: list[dict[str, str]] | None = None,
    log: Callable[[str], None] | None = None,
) -> set[str]:
    """Laedt eine Sitemap-XML und gibt alle URLs als Set zurueck.

    Unterstuetzt Sitemap-Index (rekursiv) und einfache Sitemaps.

    Args:
        sitemap_url: URL der Sitemap.
        cookies: Optionale Cookies.
        log: Optionale Log-Funktion.

    Returns:
        Set aller URLs aus der Sitemap.
    """
    if log is None:
        log = lambda msg: None

    jar = httpx.Cookies()
    for c in (cookies or []):
        jar.set(c["name"], c["value"])

    urls: set[str] = set()

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        verify=False,
        cookies=jar,
    ) as client:
        await _load_sitemap_recursive(client, sitemap_url, urls, log, depth=0)

    return urls


async def _load_sitemap_recursive(
    client: httpx.AsyncClient,
    sitemap_url: str,
    urls: set[str],
    log: Callable[[str], None],
    depth: int,
) -> None:
    """Laedt eine Sitemap rekursiv (fuer Sitemap-Indizes).

    Args:
        client: httpx Client-Instanz.
        sitemap_url: URL der Sitemap.
        urls: Set zum Sammeln der URLs.
        log: Log-Funktion.
        depth: Aktuelle Rekursionstiefe (max 3).
    """
    if depth > 3:
        log(f"  [yellow]Max Sitemap-Tiefe erreicht: {sitemap_url}[/yellow]")
        return

    try:
        response = await client.get(sitemap_url)
        if response.status_code != 200:
            log(f"  [yellow]Sitemap HTTP {response.status_code}: {sitemap_url}[/yellow]")
            return

        xml_content = response.text
    except Exception as e:
        log(f"  [yellow]Sitemap-Fehler: {friendly_error_message(e)}[/yellow]")
        return

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        log(f"  [yellow]Sitemap-XML-Fehler: {e}[/yellow]")
        return

    # Sitemap-Index: enthaelt <sitemap><loc>...</loc></sitemap>
    sub_sitemaps = root.findall(f"{{{SITEMAP_NS}}}sitemap/{{{SITEMAP_NS}}}loc")
    if not sub_sitemaps:
        # Fallback ohne Namespace
        sub_sitemaps = root.findall("sitemap/loc")

    if sub_sitemaps:
        log(f"  Sitemap-Index: {len(sub_sitemaps)} Sub-Sitemaps")
        for entry in sub_sitemaps:
            if entry.text:
                sub_url = entry.text.strip()
                await _load_sitemap_recursive(client, sub_url, urls, log, depth + 1)
        return

    # Normale Sitemap: enthaelt <url><loc>...</loc></url>
    url_entries = root.findall(f"{{{SITEMAP_NS}}}url/{{{SITEMAP_NS}}}loc")
    if not url_entries:
        # Fallback ohne Namespace
        url_entries = root.findall("url/loc")

    for entry in url_entries:
        if entry.text:
            urls.add(entry.text.strip())

    log(f"  Sitemap geladen: {len(url_entries)} URLs aus {sitemap_url}")


async def _is_valid_sitemap(client: httpx.AsyncClient, url: str) -> bool:
    """Prueft ob eine URL eine gueltige Sitemap zurueckliefert.

    Args:
        client: httpx Client-Instanz.
        url: Die zu pruefende URL.

    Returns:
        True wenn die URL HTTP 200 liefert und XML-Inhalt enthaelt.
    """
    try:
        response = await client.head(url)
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if "xml" in content_type or "text" in content_type:
                return True
            # Manche Server liefern keinen korrekten Content-Type bei HEAD
            response = await client.get(url, headers={"Range": "bytes=0-512"})
            if response.status_code in (200, 206):
                text = response.text[:512]
                return "<?xml" in text or "<urlset" in text or "<sitemapindex" in text
    except Exception:
        pass
    return False
