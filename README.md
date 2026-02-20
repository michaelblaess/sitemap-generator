# Sitemap Generator

Crawlt Websites und generiert standardkonforme `sitemap.xml` Dateien. Nutzt [Playwright](https://playwright.dev/) fuer JavaScript-Rendering oder [httpx](https://www.python-httpx.org/) fuer schnelles HTTP-Crawling.

Crawls websites and generates standard-compliant `sitemap.xml` files. Uses [Playwright](https://playwright.dev/) for JavaScript rendering or [httpx](https://www.python-httpx.org/) for fast HTTP crawling.

## Installation

### One-Liner (Standalone, kein Python noetig)

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/michaelblaess/sitemap-generator/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/michaelblaess/sitemap-generator/main/install.ps1 | iex
```

## Verwendung / Usage

```bash
# Einfach crawlen (httpx-Modus, schnell)
sitemap-generator https://example.com

# Mit JavaScript-Rendering (Playwright)
sitemap-generator https://example.com --render

# Sitemap direkt speichern
sitemap-generator https://example.com --output sitemap.xml

# Crawl-Tiefe begrenzen
sitemap-generator https://example.com --max-depth 5

# Mehr Parallelitaet
sitemap-generator https://example.com --concurrency 16

# robots.txt ignorieren
sitemap-generator https://example.com --ignore-robots

# Mit Cookies (z.B. fuer Login)
sitemap-generator https://example.com --cookie session=abc123
```

## CLI-Parameter

| Parameter | Beschreibung | Default |
|---|---|---|
| `URL` | Start-URL der Website | - |
| `--output`, `-o` | Ausgabe-Pfad fuer sitemap.xml | `sitemap_<host>_<timestamp>.xml` |
| `--max-depth`, `-d` | Maximale Crawl-Tiefe | 10 |
| `--concurrency`, `-c` | Parallele Requests | 8 |
| `--timeout`, `-t` | Timeout pro Seite (Sekunden) | 30 |
| `--render` | JavaScript mit Playwright rendern | aus |
| `--no-headless` | Browser sichtbar (Debugging) | aus |
| `--ignore-robots` | robots.txt ignorieren | aus |
| `--user-agent` | Custom User-Agent | Chrome 131 |
| `--cookie` | Cookie setzen (NAME=VALUE, mehrfach) | - |

## Tastenkuerzel (TUI)

| Taste | Funktion |
|---|---|
| `s` | Crawl starten |
| `x` | Crawl abbrechen / JSON-Fehlerbericht |
| `m` | Sitemap speichern |
| `g` | Formular-Report exportieren (JSON) |
| `j` | JIRA-Tabelle in Zwischenablage |
| `e` | Nur Fehler anzeigen |
| `b` | Seitenbaum |
| `f` | Sitemap-Diff |
| `d` | URL-Details kopieren |
| `c` | Log kopieren |
| `l` | Log ein/aus |
| `+` / `-` | Log vergroessern/verkleinern |
| `h` | History |
| `o` | robots.txt AN/AUS |
| `p` | Playwright AN/AUS |
| `i` | Info-Dialog |
| `q` | Beenden |

## Features

- **Dual-Modus**: httpx (schnell, nur HTML) oder Playwright (JavaScript-Rendering)
- **robots.txt**: Wird standardmaessig respektiert, `--ignore-robots` zum Deaktivieren
- **Auto-Split**: Bei >50.000 URLs automatisch Sitemap-Index mit Teil-Sitemaps
- **Priority**: Automatisch basierend auf Crawl-Tiefe (Startseite = 1.0)
- **lastmod**: Aus HTTP Last-Modified Header
- **URL-Normalisierung**: Duplikate durch Normalisierung vermieden
- **Formular-Erkennung**: `<form>`-Tags werden erkannt, in der Tabelle markiert und als JSON exportierbar
- **Live-TUI**: Fortschritt, Statistiken und URL-Details in Echtzeit

## Browser-Strategie

1. **System-Chrome** bevorzugt (schneller Start, weniger Speicher)
2. **Gebundeltes Chromium** als Fallback (bei Standalone-Installation enthalten)

## Datenschutz / Privacy

**Wichtig**: Das Crawlen einer Website kann je nach Umfang und Haeufigkeit vom Betreiber als ungewoehnlicher Traffic wahrgenommen werden. Bitte beachte:

- Informiere den Website-Betreiber **vor** dem Crawlen, insbesondere bei grossen Websites
- Respektiere die `robots.txt` (ist standardmaessig aktiviert)
- Setze angemessene Concurrency- und Timeout-Werte
- Dieses Tool ist fuer **eigene Websites** und **autorisierte Analysen** gedacht

**Important**: Crawling a website may be perceived as unusual traffic by the operator. Please note:

- Inform the website operator **before** crawling, especially for large websites
- Respect `robots.txt` (enabled by default)
- Use reasonable concurrency and timeout values
- This tool is intended for **your own websites** and **authorized analyses**

## Entwickler / Development

### Setup

```bash
git clone https://github.com/michaelblaess/sitemap-generator.git
cd sitemap-generator

# Windows
setup-dev-environment.bat

# Linux/macOS
./setup-dev-environment.sh
```

### Lokaler Start

```bash
# Windows
run.bat https://example.com

# Linux/macOS
./run.sh https://example.com
```

### Release erstellen

```bash
git tag v1.4.0
git push origin v1.4.0
```

GitHub Actions baut automatisch Executables fuer Windows, Linux und macOS.

## Lizenz / License

Apache License 2.0 - siehe [LICENSE](LICENSE)
