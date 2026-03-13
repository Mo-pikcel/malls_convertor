@echo off
REM ============================================================
REM  AdScreen Converter — Windows Build Script
REM  Produces: dist\AdScreen_Converter_Windows_Setup.exe
REM
REM  Run once:  build_windows.bat
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ============================================
echo   AdScreen Converter — Windows Build
echo ============================================
echo.

REM ── 1. Check Python ─────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    echo Make sure to tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

REM ── 2. Create venv ──────────────────────────────────────────
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

set PIP=.venv\Scripts\pip
set PYTHON=.venv\Scripts\python

echo Installing / updating build dependencies...
%PIP% install --quiet --upgrade pip
%PIP% install --quiet -r requirements.txt
%PIP% install --quiet pyinstaller

REM ── 3. Download FFmpeg for Windows ──────────────────────────
if not exist "bin\windows" mkdir bin\windows

if not exist "bin\windows\ffmpeg.exe" (
    echo.
    echo Downloading FFmpeg for Windows...

    REM Download ffmpeg essentials build
    set FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
    set FFMPEG_ZIP=%TEMP%\ffmpeg_win.zip

    powershell -Command "Invoke-WebRequest -Uri '!FFMPEG_URL!' -OutFile '!FFMPEG_ZIP!' -UseBasicParsing"

    echo Extracting FFmpeg...
    powershell -Command ^
        "$zip = [System.IO.Compression.ZipFile]::OpenRead('!FFMPEG_ZIP!');" ^
        "foreach ($entry in $zip.Entries) {" ^
        "  if ($entry.Name -eq 'ffmpeg.exe' -or $entry.Name -eq 'ffprobe.exe') {" ^
        "    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, 'bin\windows\' + $entry.Name, $true)" ^
        "  }" ^
        "}" ^
        "$zip.Dispose()"

    echo FFmpeg downloaded ✓
) else (
    echo FFmpeg already present in bin\windows\ -- skipping download.
)

REM ── 4. Run PyInstaller ──────────────────────────────────────
echo.
echo Building standalone app with PyInstaller...
.venv\Scripts\pyinstaller AdScreen.spec --clean --noconfirm

if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo PyInstaller build complete ✓

REM ── 5. Create installer with Inno Setup (if available) ──────
echo.
set INNO="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist %INNO% (
    echo Creating Windows installer with Inno Setup...
    %INNO% AdScreen_Setup.iss
    echo Installer created ✓
) else (
    echo Inno Setup not found — skipping installer creation.
    echo The app folder is at: dist\AdScreen Converter\
    echo You can zip and distribute that folder manually.
    echo.
    echo To create a proper .exe installer, install Inno Setup from:
    echo   https://jrsoftware.org/isdl.php
    echo Then re-run this script.
)

echo.
echo ============================================
echo   Build complete!
echo   Output: dist\AdScreen Converter\
echo ============================================
echo.
pause
