"""
build_installer.py — Build a standalone installer for מנהל שירים חכם

Usage:
    python build_installer.py

This script uses PyInstaller to package the application into a single
standalone executable.  The resulting installer will be placed in the
dist/ directory.

Prerequisites:
    pip install pyinstaller
    pip install -r requirements.txt
"""

import os
import sys
import subprocess

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MAIN_SCRIPT = os.path.join(BASE_DIR, "main.py")
ICON_PATH = os.path.join(BASE_DIR, "resources", "app_icon.ico")

# Data files that must be bundled alongside the executable
DATA_FILES = [
    "artists.txt",
    "artists_aliases.json",
    "artists_english_hidden.txt",
    "artists_english_hidden_aliases.json",
    "artists_similar_ignore.json",
    "style.qss",
    "startup_loading_window.py",
]

# ── Build configuration ───────────────────────────────────────────────

APP_NAME = "SmartSongsManager"
DISPLAY_NAME = "מנהל שירים חכם"


def build():
    """Run PyInstaller with the appropriate options."""

    # Collect --add-data flags for every data file that exists
    add_data_args = []
    for fname in DATA_FILES:
        full_path = os.path.join(BASE_DIR, fname)
        if os.path.exists(full_path):
            sep = ";" if sys.platform == "win32" else ":"
            add_data_args.extend(["--add-data", f"{full_path}{sep}."])

    # Collect resources directory if it exists
    resources_dir = os.path.join(BASE_DIR, "resources")
    if os.path.isdir(resources_dir):
        sep = ";" if sys.platform == "win32" else ":"
        add_data_args.extend(["--add-data", f"{resources_dir}{sep}resources"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",                        # no console window
        "--name", APP_NAME,
    ]

    # Add icon if available
    if os.path.isfile(ICON_PATH):
        cmd.extend(["--icon", ICON_PATH])

    cmd.extend(add_data_args)

    # Hidden imports that PyInstaller may miss
    hidden = [
        "PyQt6.QtWidgets",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "mutagen",
        "pydub",
    ]
    for h in hidden:
        cmd.extend(["--hidden-import", h])

    cmd.append(MAIN_SCRIPT)

    print("=" * 60)
    print(f"  Building {DISPLAY_NAME}")
    print("=" * 60)
    print()
    print("Command:")
    print("  " + " ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=BASE_DIR)

    if result.returncode == 0:
        dist_path = os.path.join(BASE_DIR, "dist", APP_NAME)
        print()
        print("=" * 60)
        print(f"  ✓ Build successful!")
        print(f"  Output: {dist_path}")
        print("=" * 60)
    else:
        print()
        print("=" * 60)
        print(f"  ✗ Build failed (exit code {result.returncode})")
        print("=" * 60)
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
