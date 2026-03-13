@echo off
REM AdScreen Converter — Launch (Windows)
REM Double-click this file every time you want to run the app

cd /d "%~dp0"

if not exist ".venv" (
    echo Virtual environment not found. Running setup first...
    call setup.bat
)

echo Starting AdScreen Converter...
echo Opening in your browser at http://localhost:8501
echo Press Ctrl+C to stop.
echo.

.venv\Scripts\streamlit run app.py ^
    --server.headless true ^
    --server.port 8501 ^
    --browser.gatherUsageStats false
