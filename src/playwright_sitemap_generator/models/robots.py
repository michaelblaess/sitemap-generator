"""robots.txt Parser - Prueft ob URLs gecrawlt werden duerfen."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import httpx


class RobotsChecker:
    """Laedt und parst robots.txt fuer eine Domain.

    Unterstuetzt Disallow/Allow-Regeln und Sitemap-Eintraege.
    """

    def __init__(self) -> None:
        self._rules: list[tuple[str, bool]] = []  # (path, is_allowed)
        self._sitemaps: list[str] = []
        self._loaded = False

    async def load(self, base_url: str, cookies: list[dict[str, str]] | None = None) -> None:
        """Laedt robots.txt von der angegebenen Domain.

        Args:
            base_url: Basis-URL der Website.
            cookies: Optionale Cookies.
        """
        parsed = urlparse(base_url)
        robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))

        jar = httpx.Cookies()
        for c in (cookies or []):
            jar.set(c["name"], c["value"])

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                verify=False,
                cookies=jar,
            ) as client:
                response = await client.get(robots_url)
                if response.status_code == 200:
                    self._parse(response.text)
                    self._loaded = True
        except Exception:
            # robots.txt nicht erreichbar - alles erlaubt
            self._loaded = True

    def _parse(self, text: str) -> None:
        """Parst den robots.txt Inhalt.

        Beruecksichtigt nur den User-agent: * Block.

        Args:
            text: Inhalt der robots.txt.
        """
        in_wildcard_block = False
        in_specific_block = False

        for line in text.splitlines():
            line = line.strip()

            # Kommentare entfernen
            if "#" in line:
                line = line[:line.index("#")].strip()
            if not line:
                continue

            lower = line.lower()

            # User-agent Zeilen
            if lower.startswith("user-agent:"):
                agent = line[len("user-agent:"):].strip()
                if agent == "*":
                    in_wildcard_block = True
                    in_specific_block = False
                else:
                    in_wildcard_block = False
                    in_specific_block = True
                continue

            # Nur Wildcard-Block verarbeiten
            if not in_wildcard_block or in_specific_block:
                # Sitemap-Eintraege sind global
                if lower.startswith("sitemap:"):
                    url = line[len("sitemap:"):].strip()
                    if url:
                        self._sitemaps.append(url)
                continue

            # Disallow/Allow Regeln
            if lower.startswith("disallow:"):
                path = line[len("disallow:"):].strip()
                if path:
                    self._rules.append((path, False))
            elif lower.startswith("allow:"):
                path = line[len("allow:"):].strip()
                if path:
                    self._rules.append((path, True))
            elif lower.startswith("sitemap:"):
                url = line[len("sitemap:"):].strip()
                if url:
                    self._sitemaps.append(url)

    def is_allowed(self, url: str) -> bool:
        """Prueft ob eine URL gecrawlt werden darf.

        Args:
            url: Die zu pruefende URL.

        Returns:
            True wenn die URL laut robots.txt erlaubt ist.
        """
        if not self._rules:
            return True

        path = urlparse(url).path

        # Laengste passende Regel gewinnt (spezifischste)
        best_match = ""
        allowed = True

        for rule_path, is_allowed in self._rules:
            if path.startswith(rule_path) and len(rule_path) > len(best_match):
                best_match = rule_path
                allowed = is_allowed

        return allowed

    @property
    def sitemaps(self) -> list[str]:
        """Gibt die in robots.txt gefundenen Sitemap-URLs zurueck."""
        return self._sitemaps

    @property
    def is_loaded(self) -> bool:
        """Gibt zurueck ob robots.txt geladen wurde."""
        return self._loaded
