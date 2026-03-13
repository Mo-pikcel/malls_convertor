#!/bin/bash
# AdScreen Converter — Launch (Mac / Linux)
# Run this every time: bash run.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Running setup first..."
    bash setup.sh
fi

echo "Starting AdScreen Converter..."
echo "Opening in your browser at http://localhost:8501"
echo "(Press Ctrl+C to stop)"
echo ""

.venv/bin/streamlit run app.py \
    --server.headless true \
    --server.port 8501 \
    --browser.gatherUsageStats false
