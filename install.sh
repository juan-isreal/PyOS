#!/usr/bin/env bash
set -e

REPO="juan-isreal/PyOS"
INSTALL_DIR="$HOME/.pyos"

echo "==> Checking latest release for $REPO..."

ZIP_URL=$(curl -fsSL "https://github.com" | python3 -c '
import sys, json
data = json.load(sys.stdin)
for asset in data.get("assets", []):
    if asset["name"].endswith(".zip"):
        print(asset["browser_download_url"])
        break
else:
    print(data.get("zipball_url", ""))
')

if [ -z "$ZIP_URL" ]; then
    echo "Error: Could not find a release archive for $REPO."
    exit 1
fi

echo "==> Downloading from $ZIP_URL..."
mkdir -p "$INSTALL_DIR"
curl -fsSL "$ZIP_URL" -o /tmp/pyos.zip

echo "==> Extracting to $INSTALL_DIR..."
unzip -qo /tmp/pyos.zip -d "$INSTALL_DIR"
rm -f /tmp/pyos.zip

echo "==> PyOS installed successfully!"
