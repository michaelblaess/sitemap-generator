"""Entry Point fuer Sitemap Generator."""

from __future__ import annotations

import argparse
import os
import sys

# Frozen-EXE Erkennung (PyInstaller UND Nuitka):
# PLAYWRIGHT_BROWSERS_PATH muss gesetzt werden BEVOR playwright importiert wird,
# damit das gebundelte Chromium im "browsers"-Unterordner gefunden wird.
# PyInstaller setzt sys.frozen, Nuitka setzt stattdessen __compiled__.
_is_frozen = getattr(sys, "frozen", False) or "__compiled__" in globals()
if _is_frozen:
    _exe_dir = os.path.dirname(sys.executable)
    _browsers_dir = os.path.join(_exe_dir, "browsers")
    if os.path.isdir(_browsers_dir):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browsers_dir

from textual_widgets import reset_terminal_title, set_terminal_title

from sitemap_generator import __version__
from sitemap_generator.i18n import load_locale, t
from sitemap_generator.models.settings import Settings


def main() -> None:
    """Haupteinstiegspunkt fuer die CLI."""
    # Sprache aus Settings laden (fuer CLI-Hilfe)
    settings = Settings.load()

    # Vorab --lang aus sys.argv parsen (vor argparse),
    # damit Banner und Hilfetexte uebersetzt sind
    lang = settings.language
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--lang" and i + 1 < len(sys.argv[1:]):
            lang = sys.argv[i + 2]
            break
        if arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
            break

    load_locale(lang)

    # Sprache in Settings persistieren
    if lang != settings.language:
        settings.language = lang
        settings.save()

    parser = argparse.ArgumentParser(
        prog="sitemap-generator",
        description=t("cli.banner", version=__version__),
        epilog=t("cli.examples"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "url",
        nargs="?",
        default="",
        metavar="URL",
        help=t("cli.url_help"),
    )
    parser.add_argument(
        "--output",
        "-o",
        default="",
        metavar="PATH",
        help=t("cli.output_help"),
    )
    parser.add_argument(
        "--max-depth",
        "-d",
        type=int,
        default=10,
        metavar="N",
        help=t("cli.max_depth_help"),
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=8,
        metavar="N",
        help=t("cli.concurrency_help"),
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=30,
        metavar="SEC",
        help=t("cli.timeout_help"),
    )
    parser.add_argument(
        "--render",
        action="store_true",
        default=False,
        help=t("cli.render_help"),
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        default=False,
        help=t("cli.no_headless_help"),
    )
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        default=False,
        help=t("cli.ignore_robots_help"),
    )
    parser.add_argument(
        "--user-agent",
        default="",
        metavar="UA",
        help=t("cli.user_agent_help"),
    )
    parser.add_argument(
        "--cookie",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help=t("cli.cookie_help"),
    )
    parser.add_argument(
        "--lang",
        default=lang,
        choices=["de", "en"],
        help="Sprache / Language (de, en)",
    )

    args = parser.parse_args()

    # Cookies parsen: "NAME=VALUE" -> {"name": "NAME", "value": "VALUE"}
    cookies = []
    for cookie_str in args.cookie:
        if "=" not in cookie_str:
            print(t("cli.invalid_cookie", cookie=cookie_str))
            sys.exit(1)
        name, value = cookie_str.split("=", 1)
        cookies.append({"name": name.strip(), "value": value.strip()})

    # Pruefen ob das Argument eine lokale XML-Datei ist
    sitemap_file = ""
    start_url = args.url
    if start_url and os.path.isfile(start_url) and start_url.lower().endswith(".xml"):
        sitemap_file = os.path.abspath(start_url)
        start_url = ""  # Wird aus der XML-Datei ermittelt

    from sitemap_generator.app import SitemapGeneratorApp

    # Terminal-Tab-Titel setzen - Textual macht das nicht selbst.
    set_terminal_title(f"sitemap-generator v{__version__}")
    try:
        app = SitemapGeneratorApp(
            start_url=start_url,
            sitemap_file=sitemap_file,
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
    finally:
        reset_terminal_title()


if __name__ == "__main__":
    main()
