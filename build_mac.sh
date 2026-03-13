#!/bin/bash
# ============================================================
#  AdScreen Converter — Mac Build Script
#  Produces: dist/AdScreen Converter.dmg
#
#  Run once:  bash build_mac.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================"
echo "  AdScreen Converter — Mac Build"
echo "============================================"
echo ""

# ── 1. Check Python ──────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 not found. Install from https://python.org"
    exit 1
fi

# ── 2. Check / create venv ───────────────────────────────────
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

PIP="venv/bin/pip"
PYTHON="venv/bin/python"

echo "Installing / updating build dependencies..."
$PIP install --quiet --upgrade pip
$PIP install --quiet -r requirements.txt
$PIP install --quiet pyinstaller

# ── 3. Download FFmpeg for Mac ───────────────────────────────
mkdir -p bin/mac

if [ ! -f "bin/mac/ffmpeg" ] || [ ! -f "bin/mac/ffprobe" ]; then
    echo ""
    echo "Downloading FFmpeg static binaries for Mac..."

    ARCH=$(uname -m)   # arm64 or x86_64

    if [ "$ARCH" = "arm64" ]; then
        FFMPEG_URL="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
        FFPROBE_URL="https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"
    else
        FFMPEG_URL="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
        FFPROBE_URL="https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"
    fi

    curl -L "$FFMPEG_URL"  -o /tmp/ffmpeg.zip
    curl -L "$FFPROBE_URL" -o /tmp/ffprobe.zip

    unzip -o /tmp/ffmpeg.zip  -d bin/mac/
    unzip -o /tmp/ffprobe.zip -d bin/mac/

    chmod +x bin/mac/ffmpeg bin/mac/ffprobe
    echo "FFmpeg downloaded ✓"
else
    echo "FFmpeg already present in bin/mac/ — skipping download."
fi

# ── 4. Run PyInstaller ───────────────────────────────────────
echo ""
echo "Building standalone app with PyInstaller..."
venv/bin/pyinstaller AdScreen.spec --clean --noconfirm

echo "PyInstaller build complete ✓"

# ── 5. Create .dmg ───────────────────────────────────────────
echo ""
echo "Creating .dmg installer..."

APP_PATH="dist/AdScreen Converter.app"
DMG_PATH="dist/AdScreen_Converter_Mac.dmg"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: .app bundle not found at $APP_PATH"
    exit 1
fi

# Use hdiutil to create a clean .dmg
TMP_DMG="dist/tmp_adscreen.dmg"
hdiutil create \
    -volname "AdScreen Converter" \
    -srcfolder "$APP_PATH" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

echo ""
echo "============================================"
echo "  Build complete!"
echo "  Output: $DMG_PATH"
echo ""
echo "  Distribute this .dmg file."
echo "  Users double-click it, drag the app to"
echo "  Applications, then open it."
echo "============================================"
echo ""
