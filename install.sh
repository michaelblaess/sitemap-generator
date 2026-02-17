#!/usr/bin/env bash
# Sitemap Generator - One-Line Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/michaelblaess/sitemap-generator/main/install.sh | bash
set -e

REPO="michaelblaess/sitemap-generator"
INSTALL_DIR="$HOME/.sitemap-generator"
BIN_DIR="$HOME/.local/bin"

echo "=== Sitemap Generator - Installer ==="
echo ""

# OS und Architektur erkennen
OS="$(uname -s)"
case "$OS" in
    Linux*)  PLATFORM="linux";;
    Darwin*) PLATFORM="macos";;
    *)       echo "Nicht unterstuetztes OS: $OS"; exit 1;;
esac

echo "Plattform: $PLATFORM"

# Neuestes Release von GitHub holen
echo "Suche neuestes Release..."
RELEASE_JSON=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest")

# Download-URL finden (ohne jq - grep/sed)
DOWNLOAD_URL=$(echo "$RELEASE_JSON" | grep -o "\"browser_download_url\":[[:space:]]*\"[^\"]*${PLATFORM}[^\"]*\"" | head -1 | grep -o 'https://[^"]*')

if [ -z "$DOWNLOAD_URL" ]; then
    echo "Kein Release fuer $PLATFORM gefunden!"
    echo "Bitte manuell herunterladen: https://github.com/$REPO/releases"
    exit 1
fi

VERSION=$(echo "$RELEASE_JSON" | grep -o '"tag_name":[[:space:]]*"[^"]*"' | grep -o '"v[^"]*"' | tr -d '"')
echo "Version: $VERSION"
echo "Download: $DOWNLOAD_URL"

# Altes Verzeichnis entfernen
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Herunterladen und entpacken
echo "Lade herunter..."
TMPFILE=$(mktemp)
curl -fsSL "$DOWNLOAD_URL" -o "$TMPFILE"

echo "Entpacke..."
if [[ "$DOWNLOAD_URL" == *.zip ]]; then
    unzip -qo "$TMPFILE" -d "$INSTALL_DIR"
else
    tar -xzf "$TMPFILE" -C "$INSTALL_DIR"
fi
rm -f "$TMPFILE"

# Wenn Dateien in einem Unterordner liegen, eine Ebene hochziehen
SUBDIR=$(find "$INSTALL_DIR" -maxdepth 1 -type d ! -path "$INSTALL_DIR" | head -1)
if [ -n "$SUBDIR" ]; then
    mv "$SUBDIR"/* "$INSTALL_DIR/" 2>/dev/null || true
    rmdir "$SUBDIR" 2>/dev/null || true
fi

# Executable finden und ausfuehrbar machen
chmod +x "$INSTALL_DIR/sitemap-generator" 2>/dev/null || true

# Wrapper-Skript in ~/.local/bin
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/sitemap-generator" << 'WRAPPER'
#!/usr/bin/env bash
exec "$HOME/.sitemap-generator/sitemap-generator" "$@"
WRAPPER
chmod +x "$BIN_DIR/sitemap-generator"

echo ""
echo "Installation abgeschlossen!"
echo ""

# PATH pruefen
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    echo "HINWEIS: $BIN_DIR ist nicht im PATH."
    echo "Fuege folgende Zeile zu ~/.bashrc oder ~/.zshrc hinzu:"
    echo ""
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

echo "Starten mit: sitemap-generator https://example.com"
