"""Entry Point fuer Playwright Sitemap Generator."""

from __future__ import annotations

import argparse
import os
import sys

# Frozen-EXE Erkennung (PyInstaller):
# PLAYWRIGHT_BROWSERS_PATH muss gesetzt werden BEVOR playwright importiert wird,
# damit das gebundelte Chromium im "browsers"-Unterordner gefunden wird.
if getattr(sys, "frozen", False):
    _exe_dir = os.path.dirname(sys.executable)
    _browsers_dir = os.path.join(_exe_dir, "browsers")
    if os.path.isdir(_browsers_dir):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browsers_dir

from . import __version__
from .app import SitemapGeneratorApp


BANNER = f"""
  Playwright Sitemap Generator v{__version__}
  Crawlt Websites und generiert standardkonforme sitemap.xml Dateien
"""

USAGE_EXAMPLES = """
Beispiele:
  playwright-sitemap-generator https://example.com
  playwright-sitemap-generator https://example.com --render
  playwright-sitemap-generator https://example.com --max-depth 5 --concurrency 16
  playwright-sitemap-generator https://example.com --output sitemap.xml
  playwright-sitemap-generator https://example.com --ignore-robots
  playwright-sitemap-generator https://example.com --cookie auth=token123

Tastenkuerzel in der TUI:
  s = Crawl starten    x = Crawl abbrechen    r = Sitemap speichern
  l = Log ein/aus      + / - = Log-Hoehe
  i = Info             q = Beenden
"""


def main() -> None:
    """Haupteinstiegspunkt fuer die CLI."""
    parser = argparse.ArgumentParser(
        prog="playwright-sitemap-generator",
        description=BANNER,
        epilog=USAGE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "url",
        nargs="?",
        default="",
        metavar="URL",
        help="Start-URL der Website (z.B. https://example.com)",
    )
    parser.add_argument(
        "--output", "-o",
        default="",
        metavar="PATH",
        help="Ausgabe-Pfad fuer sitemap.xml (default: sitemap.xml im CWD)",
    )
    parser.add_argument(
        "--max-depth", "-d",
        type=int,
        default=10,
        metavar="N",
        help="Maximale Crawl-Tiefe (default: 10)",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=8,
        metavar="N",
        help="Max parallele Requests (default: 8)",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        metavar="SEC",
        help="Timeout pro Seite in Sekunden (default: 30)",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        default=False,
        help="JavaScript mit Playwright rendern (langsamer, aber vollstaendiger)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        default=False,
        help="Browser sichtbar starten (Debugging)",
    )
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        default=False,
        help="robots.txt ignorieren",
    )
    parser.add_argument(
        "--user-agent",
        default="",
        metavar="UA",
        help="Custom User-Agent String",
    )
    parser.add_argument(
        "--cookie",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Cookie setzen (z.B. --cookie auth=token). Mehrfach verwendbar.",
    )

    args = parser.parse_args()

    # Cookies parsen: "NAME=VALUE" -> {"name": "NAME", "value": "VALUE"}
    cookies = []
    for cookie_str in args.cookie:
        if "=" not in cookie_str:
            print(f"Ungueltig: --cookie {cookie_str} (Format: NAME=VALUE)")
            sys.exit(1)
        name, value = cookie_str.split("=", 1)
        cookies.append({"name": name.strip(), "value": value.strip()})

    app = SitemapGeneratorApp(
        start_url=args.url,
        output_path=args.output,
        max_depth=args.max_depth,
        concurrency=args.concurrency,
        timeout=args.timeout,
        render=args.render,
        headless=not args.no_headless,
        respect_robots=not args.ignore_robots,
        user_agent=args.user_agent,
        cookies=cookies,
    )
    app.run()


if __name__ == "__main__":
    main()
