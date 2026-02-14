"""Sitemap-XML Generator - Erzeugt standardkonforme sitemap.xml Dateien."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from xml.dom import minidom

from .crawl_result import CrawlResult, PageStatus


# Max URLs pro Sitemap-Datei laut Standard
MAX_URLS_PER_SITEMAP = 50_000

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


class SitemapWriter:
    """Generiert sitemap.xml aus Crawl-Ergebnissen.

    Bei mehr als 50.000 URLs wird automatisch ein Sitemap-Index
    mit Teil-Sitemaps erstellt.
    """

    def __init__(self, results: list[CrawlResult], base_url: str = "") -> None:
        self._results = results
        self._base_url = base_url

    def write(self, output_path: str) -> list[str]:
        """Schreibt die Sitemap-Datei(en).

        Args:
            output_path: Pfad fuer die Ausgabe-Datei (z.B. sitemap.xml).

        Returns:
            Liste der geschriebenen Dateien.
        """
        # Nur erfolgreiche Seiten mit text/html in die Sitemap
        urls = [
            r for r in self._results
            if r.is_successful and self._is_html(r)
        ]

        if not urls:
            return []

        if len(urls) <= MAX_URLS_PER_SITEMAP:
            self._write_single(urls, output_path)
            return [output_path]

        return self._write_index(urls, output_path)

    def _write_single(self, urls: list[CrawlResult], path: str) -> None:
        """Schreibt eine einzelne sitemap.xml.

        Args:
            urls: Liste der URLs.
            path: Ausgabe-Pfad.
        """
        root = ET.Element("urlset")
        root.set("xmlns", SITEMAP_NS)

        for result in urls:
            url_elem = ET.SubElement(root, "url")

            loc = ET.SubElement(url_elem, "loc")
            loc.text = result.url

            if result.last_modified:
                lastmod = ET.SubElement(url_elem, "lastmod")
                lastmod.text = result.last_modified

            # Priority basierend auf Crawl-Tiefe schaetzen
            priority = ET.SubElement(url_elem, "priority")
            priority.text = self._estimate_priority(result.depth)

        self._write_pretty_xml(root, path)

    def _write_index(self, urls: list[CrawlResult], path: str) -> list[str]:
        """Schreibt einen Sitemap-Index mit Teil-Sitemaps.

        Args:
            urls: Liste aller URLs.
            path: Basis-Pfad (z.B. sitemap.xml -> sitemap-1.xml, sitemap-2.xml, ...).

        Returns:
            Liste aller geschriebenen Dateien.
        """
        base, ext = os.path.splitext(path)
        written_files: list[str] = []

        # Teil-Sitemaps schreiben
        chunks = [urls[i:i + MAX_URLS_PER_SITEMAP] for i in range(0, len(urls), MAX_URLS_PER_SITEMAP)]
        for idx, chunk in enumerate(chunks, 1):
            part_path = f"{base}-{idx}{ext}"
            self._write_single(chunk, part_path)
            written_files.append(part_path)

        # Sitemap-Index schreiben
        root = ET.Element("sitemapindex")
        root.set("xmlns", SITEMAP_NS)

        for part_path in written_files:
            sitemap_elem = ET.SubElement(root, "sitemap")
            loc = ET.SubElement(sitemap_elem, "loc")
            # Relativer Dateiname
            loc.text = os.path.basename(part_path)

        self._write_pretty_xml(root, path)
        written_files.insert(0, path)

        return written_files

    @staticmethod
    def _estimate_priority(depth: int) -> str:
        """Schaetzt die Priority basierend auf der Crawl-Tiefe.

        Tiefe 0 (Startseite) = 1.0, Tiefe 1 = 0.8, Tiefe 2 = 0.6, etc.
        Minimum: 0.1

        Args:
            depth: Crawl-Tiefe der Seite.

        Returns:
            Priority als String (z.B. "0.8").
        """
        priority = max(0.1, 1.0 - (depth * 0.2))
        return f"{priority:.1f}"

    @staticmethod
    def _is_html(result: CrawlResult) -> bool:
        """Prueft ob ein Ergebnis eine HTML-Seite ist.

        Args:
            result: Das Crawl-Ergebnis.

        Returns:
            True wenn Content-Type text/html enthaelt.
        """
        ct = result.content_type.lower()
        return "text/html" in ct or not ct

    @staticmethod
    def _write_pretty_xml(root: ET.Element, path: str) -> None:
        """Schreibt ein XML-Element huebsch formatiert in eine Datei.

        Args:
            root: XML Root-Element.
            path: Ausgabe-Pfad.
        """
        rough = ET.tostring(root, encoding="unicode", xml_declaration=False)
        pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="UTF-8")

        with open(path, "wb") as f:
            f.write(pretty)
