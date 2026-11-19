#!/usr/bin/env bash
set -e

REPO="juan-isreal/PyOS"
INSTALL_DIR="${HOME}/PyOS"

echo "==> Checking latest release for ${REPO}..."

RELEASE_JSON=$(curl -fsSL -H "User-Agent: PyOS-Installer/1.0" "https://github.com{REPO}/releases")

DOWNLOAD_URL=$(RELEASE_JSON="$RELEASE_JSON" python3 - <<'EOF'
import json, os, sys

releases = json.loads(os.getenv("RELEASE_JSON", "[]"))
if not releases:
    sys.stderr.write("No releases found on GitHub.\n")
    sys.exit(1)

latest = next(iter(releases))
tag = latest.get("tag_name", "unknown")
assets = latest.get("assets", ())
zip_asset = next((a for a in assets if a.get("name", "").endswith(".zip") and "macOS" not in a.get("name", "")), None)

if not zip_asset:
    sys.stderr.write(f"No release .zip asset found for {tag}.\n")
    sys.exit(1)

sys.stderr.write(f"==> Found latest release: {tag} ({zip_asset.get('name')})\n")
print(zip_asset.get("browser_download_url"))
EOF
)

TMP_ZIP="$(mktemp -t pyos_release.XXXXXX).zip"
echo "==> Downloading release archive..."
curl -fsSL "$DOWNLOAD_URL" -o "$TMP_ZIP"

mkdir -p "$INSTALL_DIR"
echo "==> Extracting into ${INSTALL_DIR}..."
unzip -qo "$TMP_ZIP" -d "$INSTALL_DIR"
rm -f "$TMP_ZIP"

echo "==> Installation complete! Launching PyOS..."
cd "$INSTALL_DIR"
if [ "$1" = "--cli" ]; then
    python3 main.py
else
    python3 gui.py
fi
