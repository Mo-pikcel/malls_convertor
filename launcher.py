"""
AdScreen Converter — Launcher
Entry point for PyInstaller standalone build.
Starts Streamlit server and opens the browser automatically.
"""

import os
import sys
import socket
import threading
import time
import webbrowser
from pathlib import Path


# ── Resolve paths ──────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    """Return the directory where app files live (works frozen and unfrozen)."""
    if getattr(sys, "frozen", False):
        # PyInstaller extracts everything to sys._MEIPASS at runtime
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _setup_ffmpeg():
    """Add bundled FFmpeg binaries to PATH."""
    base = _base_dir()
    if sys.platform == "win32":
        ffmpeg_dir = base / "bin" / "windows"
    else:
        ffmpeg_dir = base / "bin" / "mac"

    if ffmpeg_dir.exists():
        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
        # Make binaries executable on Mac/Linux
        if sys.platform != "win32":
            for binary in ("ffmpeg", "ffprobe"):
                p = ffmpeg_dir / binary
                if p.exists():
                    p.chmod(0o755)


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0


def _wait_and_open(port: int, timeout: int = 30):
    """Wait until Streamlit is listening then open the browser."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_free(port):
            webbrowser.open(f"http://localhost:{port}")
            return
        time.sleep(0.5)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    _setup_ffmpeg()

    base = _base_dir()
    app_path = base / "app.py"
    port = 8501

    # Open browser once Streamlit is ready
    threading.Thread(target=_wait_and_open, args=(port,), daemon=True).start()

    # Disable development mode (required when running as a PyInstaller bundle)
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    # Launch Streamlit
    sys.argv = [
        "streamlit", "run", str(app_path),
        "--server.headless=true",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
        "--server.fileWatcherType=none",
        "--global.developmentMode=false",
    ]

    from streamlit.web import cli as stcli
    stcli.main()


if __name__ == "__main__":
    main()
