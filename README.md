# Sitemap Generator

<p align="center">
  <img src="docs/flags/gb.svg" height="13" alt=""> <b>English</b> ·
  <img src="docs/flags/de.svg" height="13" alt=""> <a href="README.de.md">Deutsch</a>
</p>

---

[![Stars](https://img.shields.io/github/stars/michaelblaess/sitemap-generator?logo=github&logoColor=white&color=fbbf24)](https://github.com/michaelblaess/sitemap-generator/stargazers)
[![Forks](https://img.shields.io/github/forks/michaelblaess/sitemap-generator?logo=github&logoColor=white&color=34d399)](https://github.com/michaelblaess/sitemap-generator/network/members)
[![Issues](https://img.shields.io/github/issues/michaelblaess/sitemap-generator?logo=github&logoColor=white&color=f87171)](https://github.com/michaelblaess/sitemap-generator/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/michaelblaess/sitemap-generator?logo=github&logoColor=white&color=a78bfa)](https://github.com/michaelblaess/sitemap-generator/pulls)

[![Last Commit](https://img.shields.io/github/last-commit/michaelblaess/sitemap-generator?logo=git&logoColor=white&color=3b82f6)](https://github.com/michaelblaess/sitemap-generator/commits/main)
[![License](https://img.shields.io/badge/license-Apache_2.0-3b82f6)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-3b82f6?logo=python&logoColor=white)](https://www.python.org/)

Crawls websites and generates standard-compliant `sitemap.xml` files. Uses [Playwright](https://playwright.dev/) for JavaScript rendering or [httpx](https://www.python-httpx.org/) for fast HTTP crawling.

## Screenshots

### Main View
![Main View](docs/screenshots/01-main.png)

### Sitemap Tree
![Sitemap Tree](docs/screenshots/02-sitemap.png)

### Crawl History
![Crawl History](docs/screenshots/03-history.png)

## Installation

### One-Liner (Standalone, no Python required)

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/michaelblaess/sitemap-generator/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/michaelblaess/sitemap-generator/main/install.ps1 | iex
```

## Usage

```bash
# Simple crawl (httpx mode, fast)
sitemap-generator https://example.com

# With JavaScript rendering (Playwright)
sitemap-generator https://example.com --render

# Save sitemap directly
sitemap-generator https://example.com --output sitemap.xml

# Limit crawl depth
sitemap-generator https://example.com --max-depth 5

# More concurrency
sitemap-generator https://example.com --concurrency 16

# Ignore robots.txt
sitemap-generator https://example.com --ignore-robots

# With cookies (e.g. for login)
sitemap-generator https://example.com --cookie session=abc123
```

## CLI Parameters

| Parameter | Description | Default |
|---|---|---|
| `URL` | Start URL of the website | - |
| `--output`, `-o` | Output path for sitemap.xml | `sitemap_<host>_<timestamp>.xml` |
| `--max-depth`, `-d` | Maximum crawl depth | 10 |
| `--concurrency`, `-c` | Parallel requests | 8 |
| `--timeout`, `-t` | Timeout per page (seconds) | 30 |
| `--render` | Render JavaScript with Playwright | off |
| `--no-headless` | Browser visible (debugging) | off |
| `--ignore-robots` | Ignore robots.txt | off |
| `--user-agent` | Custom User-Agent | Chrome 131 |
| `--cookie` | Set cookie (NAME=VALUE, multiple) | - |

## Keyboard Shortcuts (TUI)

| Key | Function |
|---|---|
| `c` | Start crawl |
| `x` | Cancel crawl / JSON error report |
| `m` | Save sitemap |
| `s` | Settings |
| `g` | Export form report (JSON) |
| `j` | JIRA table to clipboard |
| `e` | Show errors only |
| `b` | Sitemap tree |
| `f` | Sitemap diff |
| `d` | Copy URL details |
| `l` | Toggle log |
| `h` | History |
| `i` | Info dialog |
| `q` | Quit |

Copying / exporting the log runs via right-click on the log panel.

## Features

- **Dual mode**: httpx (fast, HTML only) or Playwright (JavaScript rendering)
- **robots.txt**: Respected by default, `--ignore-robots` to disable
- **Auto-split**: With >50,000 URLs, an automatic sitemap index with partial sitemaps
- **Priority**: Automatically based on crawl depth (home page = 1.0)
- **lastmod**: From HTTP Last-Modified header
- **URL normalization**: Duplicates avoided through normalization
- **Form detection**: `<form>` tags are detected, marked in the table and exportable as JSON
- **Live TUI**: Progress, statistics and URL details in real time
- **Resizable panels**: Splitters to freely resize the URL table, log and stats panels
- **Log panel**: Right-click context menu — copy, export to file, or hide
- **Settings dialog**: Language, robots.txt, Playwright, concurrency, timeout and crawl depth — persisted across runs
- **Filter with history**: Filter the URL table by URL/status; recent filter terms in a dropdown

## Browser Strategy

1. **System Chrome** preferred (faster startup, less memory)
2. **Bundled Chromium** as fallback (included in standalone installation)

## Privacy

**Important**: Crawling a website may be perceived as unusual traffic by the operator. Please note:

- Inform the website operator **before** crawling, especially for large websites
- Respect `robots.txt` (enabled by default)
- Use reasonable concurrency and timeout values
- This tool is intended for **your own websites** and **authorized analyses**

## Development

### Setup

```bash
git clone https://github.com/michaelblaess/sitemap-generator.git
cd sitemap-generator

# Windows
setup-dev-environment.bat

# Linux/macOS
./setup-dev-environment.sh
```

### Local Start

```bash
# Windows
run.bat https://example.com

# Linux/macOS
./run.sh https://example.com
```

### Creating a Release

```bash
git tag v1.9.0
git push origin v1.9.0
```

GitHub Actions automatically builds executables for Windows, Linux and macOS.

## License

Apache License 2.0 - see [LICENSE](LICENSE)
