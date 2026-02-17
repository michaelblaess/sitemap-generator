"""Fehlerbericht-Generator - Erzeugt JSON-Reports und JIRA-Tabellen fuer Dead Links."""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlparse

from ..models.crawl_result import CrawlResult, CrawlStats, PageStatus


class Reporter:
    """Erzeugt Fehlerberichte aus Crawl-Ergebnissen.

    Der Report enthaelt alle URLs mit HTTP-Fehler (4xx/5xx),
    Timeouts und sonstigen Fehlern, inklusive der Seiten
    die auf die fehlerhafte URL verlinken.
    """

    @staticmethod
    def save_error_report(
        results: list[CrawlResult],
        stats: CrawlStats,
        start_url: str,
        output_path: str,
    ) -> str:
        """Erzeugt und speichert einen JSON-Fehlerbericht.

        Args:
            results: Alle Crawl-Ergebnisse.
            stats: Crawl-Statistiken.
            start_url: Start-URL des Crawls.
            output_path: Pfad fuer die JSON-Datei.

        Returns:
            Pfad der geschriebenen Datei.
        """
        errors = [
            r for r in results
            if r.http_status_code >= 400
            or r.status in (PageStatus.ERROR, PageStatus.TIMEOUT)
        ]

        report = {
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "start_url": start_url,
            "summary": {
                "total_crawled": stats.total_crawled,
                "total_discovered": stats.total_discovered,
                "total_errors": stats.total_errors,
                "total_2xx": stats.total_2xx,
                "total_3xx": stats.total_3xx,
                "total_4xx": stats.total_4xx,
                "total_5xx": stats.total_5xx,
                "duration": stats.duration_display,
            },
            "dead_links": [
                {
                    "url": r.url,
                    "http_status": r.http_status_code,
                    "status": r.status.value,
                    "error_message": r.error_message,
                    "referring_pages": r.referring_pages,
                }
                for r in errors
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return output_path

    @staticmethod
    def generate_jira_table(results: list[CrawlResult], start_url: str) -> str:
        """Erzeugt eine JIRA-Wiki-Markup-Tabelle mit allen Fehler-URLs.

        Filtert nur URLs mit HTTP 4xx/5xx, ERROR oder TIMEOUT Status
        und formatiert sie als JIRA-Wiki-Tabelle mit verweisenden Seiten.

        Args:
            results: Alle Crawl-Ergebnisse.
            start_url: Start-URL des Crawls.

        Returns:
            JIRA-Wiki-Markup-String fuer die Zwischenablage.
        """
        errors = [
            r for r in results
            if r.http_status_code >= 400
            or r.status in (PageStatus.ERROR, PageStatus.TIMEOUT)
        ]

        if not errors:
            return ""

        lines = ["||URL||HTTP||Fehler||Verweisende Seiten||"]

        for r in errors:
            http_code = str(r.http_status_code) if r.http_status_code else "-"
            status = r.status.value

            if r.referring_pages:
                refs = []
                for ref in r.referring_pages:
                    link_text = ref.get("link_text", "").strip()
                    ref_url = ref.get("url", "")
                    if link_text:
                        # Linktext + URL getrennt (kein [text|url] Format,
                        # da Pipe in JIRA-Tabellenzellen als Zellseparator
                        # interpretiert wird und Links bricht)
                        refs.append(f'"{link_text}" [{ref_url}]')
                    else:
                        # Kein Linktext: nur URL als klickbaren Link
                        refs.append(f"[{ref_url}]")
                referring = " \\\\ ".join(refs)
            else:
                referring = "-"

            # URL in erster Spalte als klickbaren JIRA-Link formatieren
            lines.append(f"|[{r.url}]|{http_code}|{status}|{referring}|")

        return "\n".join(lines)
