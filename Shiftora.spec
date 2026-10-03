# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for Shiftora.

Used by build_windows.bat / build_linux.sh and by the GitHub release workflow:

    pyinstaller --noconfirm Shiftora.spec
"""

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821 - provided by PyInstaller
APP_NAME = "Shiftora"

block_cipher = None

a = Analysis(  # noqa: F821 - provided by PyInstaller
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "assets"), "assets"),
    ],
    hiddenimports=[
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "numpy",
        "pandas",
        "IPython",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe_kwargs = dict(
    pyz=pyz,
    a_scripts=a.scripts,
    a_binaries=[],
    a_zipfiles=[],
    a_datas=[],
    exclude_binaries=True,  # one-directory mode: COLLECT() gathers the files
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == "darwin":
    exe_kwargs["argv_emulation"] = False

# Windows embeds icon.ico into the .exe. On Linux/macOS PyInstaller's EXE
# target does not accept a PNG icon, so the icon is simply bundled via
# `datas` (see Analysis above) and applied at runtime instead.
if os.name == "nt" and (ROOT / "assets" / "icon.ico").exists():
    exe_kwargs["icon"] = str(ROOT / "assets" / "icon.ico")

exe = EXE(**exe_kwargs)  # noqa: F821

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
