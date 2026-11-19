#!/usr/bin/env bash
set -e

BUMP_TYPE="${1:-beta}"
NOTES="${2:-}"

if [ ! -f VERSION ]; then
    echo "0.1.0-beta.1" > VERSION
fi

CURRENT=$(tr -d '[:space:]' < VERSION)

NEXT_VER=$(python3 - "$CURRENT" "$BUMP_TYPE" <<'EOF'
import re, sys

cur, bump = sys.argv[1], sys.argv[2].lower()

if re.match(r"^\d+\.\d+\.\d+(-[a-z0-9.]+)?$", bump):
    print(bump)
    sys.exit(0)

m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$", cur)
if not m:
    print("0.1.0-beta.1")
    sys.exit(0)

major, minor, patch, beta = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)

if bump == "beta":
    next_beta = (int(beta) + 1) if beta is not None else 1
    print(f"{major}.{minor}.{patch}-beta.{next_beta}")
elif bump == "patch":
    print(f"{major}.{minor}.{patch + 1}-beta.1")
elif bump == "minor":
    print(f"{major}.{minor + 1}.0-beta.1")
elif bump in ("major", "1.0"):
    print(f"{major + 1}.0.0" if major >= 1 else "1.0.0")
else:
    sys.stderr.write("Usage: ./release.sh [beta | patch | minor | 1.0 | <exact_version>] [\"Release notes\"]\n")
    sys.exit(1)
EOF
)

TAG="v${NEXT_VER}"
NOTES="${NOTES:-PyOS ${TAG} release}"

echo "==> Bumping version: ${CURRENT} -> ${NEXT_VER} (${TAG})"
echo "$NEXT_VER" > VERSION

mkdir -p dist
rm -rf dist/*

python3 -m compileall -q gui.py main.py system_cmds.py utils.py tsdk.py commands/
ZIP_PATH="dist/PyOS-${TAG}.zip"
zip -rq "$ZIP_PATH" VERSION gui.py main.py system_cmds.py utils.py tsdk.py registry.json README.md LICENSE commands/ -x "*/__pycache__/*" "*.DS_Store"
echo "==> Built archive: $ZIP_PATH"

ASSETS=("$ZIP_PATH")
if command -v pyinstaller >/dev/null 2>&1; then
    echo "==> Compiling standalone native app with PyInstaller..."
    pyinstaller --noconfirm --onefile --windowed --name "PyOS-${TAG}" --add-data "commands:commands" --add-data "registry.json:." --add-data "VERSION:." gui.py >/dev/null 2>&1
    if [ -d "dist/PyOS-${TAG}.app" ]; then
        zip -rq "dist/PyOS-${TAG}-macOS.zip" "dist/PyOS-${TAG}.app"
        ASSETS+=("dist/PyOS-${TAG}-macOS.zip")
    elif [ -f "dist/PyOS-${TAG}" ]; then
        ASSETS+=("dist/PyOS-${TAG}")
    fi
fi

git add VERSION
git commit -m "Release ${TAG}"
git tag -a "$TAG" -m "$NOTES"
git push origin HEAD --tags

if command -v gh >/dev/null 2>&1; then
    PRERELEASE_FLAG=""
    if [[ "$NEXT_VER" == *"-beta"* ]]; then
        PRERELEASE_FLAG="--prerelease"
    fi
    gh release create "$TAG" "${ASSETS[@]}" --title "PyOS ${TAG}" --notes "$NOTES" $PRERELEASE_FLAG
    echo "==> Published PyOS ${TAG} live on GitHub Releases!"
else
    echo "==> Tagged & pushed ${TAG}. Install 'gh' CLI for 1-click uploads or upload ${ZIP_PATH} on GitHub Releases."
fi
