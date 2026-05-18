# Sitemap Generator

<p align="center">
  <img src="docs/flags/gb.svg" height="13" alt=""> <a href="README.md">English</a> ·
  <img src="docs/flags/de.svg" height="13" alt=""> <b>Deutsch</b>
</p>

---

[![Stars](https://img.shields.io/github/stars/michaelblaess/sitemap-generator?logo=github&logoColor=white&color=fbbf24)](https://github.com/michaelblaess/sitemap-generator/stargazers)
[![Forks](https://img.shields.io/github/forks/michaelblaess/sitemap-generator?logo=github&logoColor=white&color=34d399)](https://github.com/michaelblaess/sitemap-generator/network/members)
[![Issues](https://img.shields.io/github/issues/michaelblaess/sitemap-generator?logo=github&logoColor=white&color=f87171)](https://github.com/michaelblaess/sitemap-generator/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/michaelblaess/sitemap-generator?logo=github&logoColor=white&color=a78bfa)](https://github.com/michaelblaess/sitemap-generator/pulls)

[![Last Commit](https://img.shields.io/github/last-commit/michaelblaess/sitemap-generator?logo=git&logoColor=white&color=3b82f6)](https://github.com/michaelblaess/sitemap-generator/commits/main)
[![License](https://img.shields.io/badge/license-Apache_2.0-3b82f6)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-3b82f6?logo=python&logoColor=white)](https://www.python.org/)

Crawlt Websites und generiert standardkonforme `sitemap.xml` Dateien. Nutzt [Playwright](https://playwright.dev/) für JavaScript-Rendering oder [httpx](https://www.python-httpx.org/) für schnelles HTTP-Crawling.

## Screenshots

### Hauptansicht
![Hauptansicht](docs/screenshots/01-main.png)

### Seitenbaum
![Seitenbaum](docs/screenshots/02-sitemap.png)

### Crawl-History
![Crawl-History](docs/screenshots/03-history.png)

## Installation

### One-Liner (Standalone, kein Python nötig)

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/michaelblaess/sitemap-generator/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/michaelblaess/sitemap-generator/main/install.ps1 | iex
```

## Verwendung

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
| `--output`, `-o` | Ausgabe-Pfad für sitemap.xml | `sitemap_<host>_<timestamp>.xml` |
| `--max-depth`, `-d` | Maximale Crawl-Tiefe | 10 |
| `--concurrency`, `-c` | Parallele Requests | 8 |
| `--timeout`, `-t` | Timeout pro Seite (Sekunden) | 30 |
| `--render` | JavaScript mit Playwright rendern | aus |
| `--no-headless` | Browser sichtbar (Debugging) | aus |
| `--ignore-robots` | robots.txt ignorieren | aus |
| `--user-agent` | Custom User-Agent | Chrome 131 |
| `--cookie` | Cookie setzen (NAME=VALUE, mehrfach) | - |

## Tastenkürzel (TUI)

| Taste | Funktion |
|---|---|
| `c` | Crawl starten |
| `x` | Crawl abbrechen / JSON-Fehlerbericht |
| `m` | Sitemap speichern |
| `s` | Einstellungen |
| `g` | Formular-Report exportieren (JSON) |
| `j` | JIRA-Tabelle in Zwischenablage |
| `e` | Nur Fehler anzeigen |
| `b` | Seitenbaum |
| `f` | Sitemap-Diff |
| `d` | URL-Details kopieren |
| `l` | Log ein/aus |
| `h` | History |
| `i` | Info-Dialog |
| `q` | Beenden |

Log kopieren / exportieren läuft über Rechtsklick auf das Log-Panel.

## Features

- **Dual-Modus**: httpx (schnell, nur HTML) oder Playwright (JavaScript-Rendering)
- **robots.txt**: Wird standardmäßig respektiert, `--ignore-robots` zum Deaktivieren
- **Auto-Split**: Bei >50.000 URLs automatisch Sitemap-Index mit Teil-Sitemaps
- **Priority**: Automatisch basierend auf Crawl-Tiefe (Startseite = 1.0)
- **lastmod**: Aus HTTP Last-Modified Header
- **URL-Normalisierung**: Duplikate durch Normalisierung vermieden
- **Formular-Erkennung**: `<form>`-Tags werden erkannt, in der Tabelle markiert und als JSON exportierbar
- **Live-TUI**: Fortschritt, Statistiken und URL-Details in Echtzeit
- **Anpassbare Panels**: Splitter zum freien Anpassen von URL-Tabelle, Log und Statistik-Panel
- **Log-Panel**: Rechtsklick-Kontextmenü — kopieren, in Datei exportieren oder ausblenden
- **Einstellungen-Dialog**: Sprache, robots.txt, Playwright, Concurrency, Timeout und Crawl-Tiefe — dauerhaft gespeichert
- **Filter mit Verlauf**: URL-Tabelle nach URL/Status filtern; letzte Filterbegriffe im Dropdown

## Browser-Strategie

1. **System-Chrome** bevorzugt (schnellerer Start, weniger Speicher)
2. **Gebündeltes Chromium** als Fallback (bei Standalone-Installation enthalten)

## Datenschutz

**Wichtig**: Das Crawlen einer Website kann je nach Umfang und Häufigkeit vom Betreiber als ungewöhnlicher Traffic wahrgenommen werden. Bitte beachte:

- Informiere den Website-Betreiber **vor** dem Crawlen, insbesondere bei großen Websites
- Respektiere die `robots.txt` (ist standardmäßig aktiviert)
- Setze angemessene Concurrency- und Timeout-Werte
- Dieses Tool ist für **eigene Websites** und **autorisierte Analysen** gedacht

## Entwickler

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
git tag v1.9.0
git push origin v1.9.0
```

GitHub Actions baut automatisch Executables für Windows, Linux und macOS.

## Lizenz

Apache License 2.0 - siehe [LICENSE](LICENSE)
