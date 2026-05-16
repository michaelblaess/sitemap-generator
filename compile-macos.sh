#!/usr/bin/env bash
# compile-macos.sh - compiles sitemap-generator into a standalone macOS binary
# with Nuitka, with a bundled Chromium browser.
#
# Output: dist/sitemap-generator/sitemap-generator + browsers/, and
# dist/sitemap-generator-vX.Y.Z-macos-<arch>.tar.gz ready to hand out.
#
# Build machine needs the Xcode Command Line Tools (clang): xcode-select --install
#
# Nuitka ad-hoc signs the binary automatically. On download, macOS quarantines
# it - the recipient clears it once: xattr -dr com.apple.quarantine sitemap-generator
# No .app bundle (this is a TUI). The arch (arm64/x86_64) is host-bound.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
entry="$root/src/sitemap_generator/__main__.py"
init_py="$root/src/sitemap_generator/__init__.py"
out_dir="$root/dist"
dist_dir="$out_dir/sitemap-generator"
arch="$(uname -m)"   # arm64 (Apple Silicon) oder x86_64 (Intel)

if ! command -v clang >/dev/null 2>&1; then
    echo "Fehlt: clang - bitte Xcode Command Line Tools installieren: xcode-select --install" >&2
    exit 1
fi

# venv mit dem Lockfile abgleichen - VOR der python-Ermittlung, damit .venv
# auch bei einem frischen Checkout (z.B. CI) existiert.
if command -v uv >/dev/null 2>&1; then
    echo "Syncing venv (uv sync --inexact)..."
    uv sync --inexact --project "$root"
fi

if [ -x "$root/.venv/bin/python" ]; then
    python="$root/.venv/bin/python"
else
    python="python3"
fi

# Chromium pruefen/aktualisieren (idempotent - laedt nur bei Bedarf)
echo "Checking Playwright Chromium..."
"$python" -m playwright install chromium

# portables sed - 'grep -oP' gibt es auf dem BSD-grep von macOS nicht
version="$(sed -n 's/^__version__ *= *"\([^"]*\)".*/\1/p' "$init_py")"
if [ -z "$version" ]; then
    echo "Konnte __version__ nicht aus $init_py lesen" >&2
    exit 1
fi

echo "Compiling sitemap-generator v$version ($arch) with Nuitka..."
rm -rf "$dist_dir"
started=$(date +%s)

# Den Playwright-Node-Treiber NICHT explizit einschliessen - das macht Nuitkas
# eingebautes playwright-Plugin. Ein zusaetzliches --include-package-data=
# playwright kollidiert mit dem Plugin ("data file
# 'playwright/driver/node' conflicts with exe").
"$python" -m nuitka \
    --standalone \
    --assume-yes-for-downloads \
    --remove-output \
    --include-package=sitemap_generator \
    --include-package-data=sitemap_generator \
    --output-dir="$out_dir" \
    --output-filename=sitemap-generator \
    "$entry"

if [ -d "$out_dir/__main__.dist" ]; then
    mv "$out_dir/__main__.dist" "$dist_dir"
fi

# Nur die neueste Headless-Shell mitbuendeln (~265 MB). Alle Use-Cases laufen
# headless (Azure-Pipeline + Standalone-Terminal-TUI) - das volle Chromium
# (~407 MB) wird nie gebraucht. --no-headless faellt auf System-Chrome zurueck.
echo "Bundling Chromium headless shell..."
browsers_dir="$dist_dir/browsers"
mkdir -p "$browsers_dir"
cache="${HOME}/Library/Caches/ms-playwright"
latest="$(ls -d "$cache/chromium_headless_shell-"* 2>/dev/null | sort -V | tail -1)"
if [ ! -d "$latest" ]; then
    echo "Kein chromium_headless_shell im Playwright-Cache gefunden" >&2
    exit 1
fi
cp -r "$latest" "$browsers_dir/"

elapsed=$(( $(date +%s) - started ))
size_mb=$(du -sm "$dist_dir" | cut -f1)

tarball="$out_dir/sitemap-generator-v$version-macos-$arch.tar.gz"
rm -f "$tarball"
tar -czf "$tarball" -C "$out_dir" sitemap-generator
tar_mb=$(du -sm "$tarball" | cut -f1)

echo ""
echo "Done in ${elapsed}s"
echo "  dist folder : $dist_dir  (${size_mb} MB)"
echo "  tarball     : $tarball  (${tar_mb} MB)"
