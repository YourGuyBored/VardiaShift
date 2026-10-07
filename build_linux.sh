#!/usr/bin/env bash
# =====================================================================
# VardiaShift - Linux build script
#
# Builds a distributable folder:  dist/VardiaShift/VardiaShift
#
# Requirements: Python 3.10+.
# Usage:
#     ./build_linux.sh
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 was not found on PATH."
    exit 1
fi

echo "[1/4] Creating build environment..."
if [ ! -d .build-venv ]; then
    python3 -m venv .build-venv
fi
# shellcheck disable=SC1091
source .build-venv/bin/activate

echo "[2/4] Installing dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

echo "[3/4] Building VardiaShift with PyInstaller..."
pyinstaller --noconfirm VardiaShift.spec

echo "[4/4] Packaging release archive..."
rm -f "dist/VardiaShift-Linux-x64.tar.gz"
tar -czf "dist/VardiaShift-Linux-x64.tar.gz" -C dist VardiaShift

echo
echo "====================================================================="
echo " BUILD COMPLETE"
echo
echo " Executable folder : dist/VardiaShift/VardiaShift"
echo " Release archive   : dist/VardiaShift-Linux-x64.tar.gz"
echo "====================================================================="
