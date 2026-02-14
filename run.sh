#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "Bitte zuerst setup-dev-environment.sh ausfuehren!"
    exit 1
fi
.venv/bin/python -m playwright_sitemap_generator "$@"
