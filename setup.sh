#!/bin/bash
# AdScreen Converter — First-time setup (Mac / Linux)
# Run this once: bash setup.sh

set -e

echo ""
echo "==================================="
echo "  AdScreen Converter — Setup"
echo "==================================="
echo ""

# ── Check Python ──────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Download it from https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python $PYTHON_VERSION found."

# ── Check FFmpeg ──────────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
    echo ""
    echo "WARNING: FFmpeg is not installed — it is required to convert videos."
    echo ""
    echo "Install it with:"
    echo "  Mac:   brew install ffmpeg"
    echo "  Linux: sudo apt install ffmpeg"
    echo ""
    read -p "Continue setup anyway? (y/n): " CONT
    [[ "$CONT" != "y" ]] && exit 1
else
    echo "FFmpeg found."
fi

# ── Create virtual environment ────────────────────────
if [ ! -d ".venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# ── Install dependencies ──────────────────────────────
echo "Installing Python packages..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

echo ""
echo "==================================="
echo "  Setup complete!"
echo "  Run the app with:  bash run.sh"
echo "==================================="
echo ""
