# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for Shiftora.

Used by build_windows.bat / build_linux.sh and by the GitHub release workflow:

    pyinstaller --noconfirm Shiftora.spec

NOTE: EXE() arguments are intentionally positional (pyz, scripts, binaries,
zipfiles, datas) - this is the canonical one-directory form. A keyword-style
variant was found to silently drop the .pyz archive from the bundle.
"""

import os
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

# Windows embeds icon.ico into the .exe. On Linux/macOS the icon is bundled
# via `datas` (see Analysis above) and applied at runtime instead.
exe_icon = (
    str(ROOT / "assets" / "icon.ico")
    if os.name == "nt" and (ROOT / "assets" / "icon.ico").exists()
    else None
)

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
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
    icon=exe_icon,
)

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
