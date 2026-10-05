#!/usr/bin/env python3
"""
MediaMTX Launcher Helper
Locates mediamtx executable and runs it with production/mediamtx.yml
"""
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "mediamtx.yml")

CANDIDATES = [
    shutil.which("mediamtx"),
    r"C:\Users\saran\Downloads\mediamtx_v1.21.1_windows_amd64\mediamtx.exe",
    r"C:\Users\saran\OneDrive\Desktop\Saakh\camera STream\e88-streaming\.venv\Scripts\mediamtx.exe",
    os.path.join(BASE_DIR, "mediamtx.exe"),
]

def find_mediamtx() -> str:
    for c in CANDIDATES:
        if c and os.path.isfile(c):
            return c
    raise FileNotFoundError("Could not find mediamtx executable. Ensure mediamtx is on PATH or in production/")

if __name__ == "__main__":
    exe = find_mediamtx()
    print(f"Found MediaMTX at: {exe}")
    print(f"Loading config: {CONFIG_FILE}")
    cmd = [exe, CONFIG_FILE]
    sys.exit(subprocess.call(cmd))
