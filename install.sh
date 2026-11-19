#!/usr/bin/env bash
set -e

REPO="juan-isreal/PyOS"
INSTALL_DIR="$HOME/.pyos"
HOST="api.github.com"
API_URL="https://${HOST}/repos/${REPO}/releases?per_page=1"

echo "==> Checking latest release for $REPO..."

ZIP_URL=$(curl -fsSL -H "User-Agent: PyOS-Installer" "$API_URL" | python3 -c '
import sys, json
releases = json.load(sys.stdin)
data = releases[0] if releases else {}
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
unzip -qo /tmp/pyos.zip -d /tmp/pyos_extract
cp -R /tmp/pyos_extract/*/* "$INSTALL_DIR/" 2>/dev/null || cp -R /tmp/pyos_extract/* "$INSTALL_DIR/"
rm -rf /tmp/pyos.zip /tmp/pyos_extract

echo "==> PyOS installed successfully!"
