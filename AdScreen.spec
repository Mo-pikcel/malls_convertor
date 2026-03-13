# -*- mode: python ; coding: utf-8 -*-
"""
AdScreen Converter — PyInstaller spec
Build with:  pyinstaller AdScreen.spec
"""

import sys
from pathlib import Path
import streamlit
from PyInstaller.utils.hooks import copy_metadata, collect_data_files

SPEC_DIR   = Path(SPECPATH)
ST_DIR     = Path(streamlit.__file__).parent

block_cipher = None

# ── Package metadata (fixes importlib.metadata.PackageNotFoundError) ───────────
datas = []
for pkg in [
    "streamlit", "altair", "click", "packaging", "pydeck",
    "pyarrow", "tornado", "watchdog", "gitpython", "rich",
    "pillow", "opencv-python-headless",
]:
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# ── App source and assets ──────────────────────────────────────────────────────
datas += [
    # App source files
    (str(SPEC_DIR / "app.py"),        "."),
    (str(SPEC_DIR / "core.py"),       "."),
    (str(SPEC_DIR / "smart_crop.py"), "."),
    (str(SPEC_DIR / "export_comps.jsx"), "."),

    # Templates folder
    (str(SPEC_DIR / "templates"), "templates"),

    # Logo / images
    (str(SPEC_DIR / "img"), "img"),

    # Streamlit static assets (required for the web UI to render)
    (str(ST_DIR / "static"),   "streamlit/static"),
    (str(ST_DIR / "runtime"),  "streamlit/runtime"),

    # FFmpeg binaries (place in bin/mac and bin/windows before building)
    (str(SPEC_DIR / "bin"), "bin"),
]

# ── Hidden imports Streamlit needs ─────────────────────────────────────────────
hiddenimports = [
    # Streamlit internals
    "streamlit",
    "streamlit.web.cli",
    "streamlit.web.server",
    "streamlit.runtime",
    "streamlit.runtime.scriptrunner",
    "streamlit.components.v1",

    # App dependencies
    "cv2",
    "PIL",
    "PIL.Image",
    "numpy",
    "pathlib",
    "zipfile",
    "shutil",
    "logging",
    "dataclasses",

    # AI dependencies (optional — bundled if installed)
    "ultralytics",
    "easyocr",
    "torch",
    "torchvision",
]

a = Analysis(
    [str(SPEC_DIR / "launcher.py")],
    pathex=[str(SPEC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "notebook"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AdScreen Converter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # Disabled — UPX corrupts some bundled modules
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(SPEC_DIR / "img" / ("adscreen.icns" if sys.platform == "darwin" else "adscreen.ico")),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,                # Disabled — UPX corrupts some bundled modules
    upx_exclude=[],
    name="AdScreen Converter",
)

# ── Mac .app bundle ────────────────────────────────────────────────────────────
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="AdScreen Converter.app",
        icon=str(SPEC_DIR / "img" / ("adscreen.icns" if sys.platform == "darwin" else "adscreen.ico")),
        bundle_identifier="com.primedia.adscreen",
        info_plist={
            "CFBundleDisplayName": "AdScreen Converter",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription": "Not required",
        },
    )
