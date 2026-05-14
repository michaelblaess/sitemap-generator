"""Sitemap-Autodiscovery und -Loader.

Findet die offizielle Sitemap einer Website automatisch und laedt alle
enthaltenen URLs. Wird verwendet um gecrawlte URLs mit der offiziellen
Sitemap abzugleichen. Kann auch lokale XML-Dateien einlesen.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections.abc import Callable
from urllib.parse import urlparse, urlunparse

import httpx

from ..i18n import t
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
    for c in cookies or []:
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
                log(t("sitemap_reader.check_robots", url=sitemap_url))
                if await _is_valid_sitemap(client, sitemap_url):
                    log(t("sitemap_reader.found", url=sitemap_url))
                    return sitemap_url
                log(t("sitemap_reader.unreachable", url=sitemap_url))

        # Phase 2: Typische Pfade durchprobieren
        log(t("sitemap_reader.trying_paths"))
        for path in _COMMON_SITEMAP_PATHS:
            candidate = f"{origin}{path}"
            log(t("sitemap_reader.testing", url=candidate))
            if await _is_valid_sitemap(client, candidate):
                log(t("sitemap_reader.found", url=candidate))
                return candidate

    log(t("sitemap_reader.not_found"))
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
    for c in cookies or []:
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
        log(t("sitemap_reader.max_depth", url=sitemap_url))
        return

    try:
        response = await client.get(sitemap_url)
        if response.status_code != 200:
            log(t("sitemap_reader.http_error", code=response.status_code, url=sitemap_url))
            return

        xml_content = response.text
    except Exception as e:
        log(t("sitemap_reader.fetch_error", error=friendly_error_message(e)))
        return

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        log(t("sitemap_reader.xml_error", error=e))
        return

    # Sitemap-Index: enthaelt <sitemap><loc>...</loc></sitemap>
    sub_sitemaps = root.findall(f"{{{SITEMAP_NS}}}sitemap/{{{SITEMAP_NS}}}loc")
    if not sub_sitemaps:
        # Fallback ohne Namespace
        sub_sitemaps = root.findall("sitemap/loc")

    if sub_sitemaps:
        log(t("sitemap_reader.index_count", count=len(sub_sitemaps)))
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

    log(t("sitemap_reader.loaded", count=len(url_entries), url=sitemap_url))


def load_sitemap_from_file(
    file_path: str,
    log: Callable[[str], None] | None = None,
) -> tuple[str, set[str]]:
    """Laedt eine lokale Sitemap-XML-Datei und gibt Basis-URL + URLs zurueck.

    Liest die XML-Datei, extrahiert alle <loc>-Eintraege und ermittelt die
    gemeinsame Basis-URL aus den gefundenen URLs.

    Args:
        file_path: Pfad zur lokalen XML-Datei.
        log: Optionale Log-Funktion.

    Returns:
        Tuple aus (basis_url, set_der_urls). Bei Fehler ("", leeres Set).
    """
    if log is None:
        log = lambda msg: None

    if not os.path.isfile(file_path):
        log(t("sitemap_reader.file_not_found", path=file_path))
        return "", set()

    try:
        with open(file_path, encoding="utf-8") as f:
            xml_content = f.read()
    except Exception as e:
        log(t("sitemap_reader.file_read_error", error=e))
        return "", set()

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        log(t("sitemap_reader.file_xml_error", error=e))
        return "", set()

    # URLs extrahieren (mit und ohne Namespace)
    url_entries = root.findall(f"{{{SITEMAP_NS}}}url/{{{SITEMAP_NS}}}loc")
    if not url_entries:
        url_entries = root.findall("url/loc")

    urls: set[str] = set()
    for entry in url_entries:
        if entry.text:
            urls.add(entry.text.strip())

    if not urls:
        log(t("sitemap_reader.file_no_urls"))
        return "", set()

    # Basis-URL aus den URLs ermitteln (Schema + Domain der ersten URL)
    first_url = next(iter(urls))
    parsed = urlparse(first_url)
    base_url = urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))

    log(t("sitemap_reader.file_loaded", count=len(urls)))
    log(t("sitemap_reader.file_base_url", url=base_url))

    return base_url, urls


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
