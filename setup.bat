@echo off
REM AdScreen Converter — First-time setup (Windows)
REM Double-click this file once to set up everything

echo.
echo ===================================
echo   AdScreen Converter — Setup
echo ===================================
echo.

REM ── Check Python ─────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed.
    echo Download it from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
echo Python found.

REM ── Check FFmpeg ──────────────────────────────────────
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: FFmpeg is not installed.
    echo The easiest way to install it on Windows:
    echo   winget install ffmpeg
    echo Or download from https://ffmpeg.org/download.html
    echo Extract it and add the bin\ folder to your system PATH.
    echo.
    pause
)

REM ── Create virtual environment ────────────────────────
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM ── Upgrade pip ───────────────────────────────────────
echo Upgrading pip...
.venv\Scripts\python -m pip install --upgrade pip --quiet

REM ── Install core dependencies ─────────────────────────
echo Installing core packages (Streamlit, Flet)...
.venv\Scripts\pip install streamlit flet --quiet --timeout 120

REM ── Install OpenCV ────────────────────────────────────
echo Installing OpenCV...
.venv\Scripts\pip install opencv-python-headless --quiet --timeout 120

REM ── Install PyTorch (CPU) ─────────────────────────────
echo Installing PyTorch (this may take a few minutes)...
.venv\Scripts\pip install torch torchvision --quiet --timeout 300 --retries 5

REM ── Install YOLOv8 ────────────────────────────────────
echo Installing YOLOv8...
.venv\Scripts\pip install ultralytics --quiet --timeout 120

REM ── Install EasyOCR ───────────────────────────────────
echo Installing EasyOCR...
.venv\Scripts\pip install easyocr --quiet --timeout 120

echo.
echo ===================================
echo   Setup complete!
echo   Run the app: double-click run.bat
echo ===================================
echo.
pause
