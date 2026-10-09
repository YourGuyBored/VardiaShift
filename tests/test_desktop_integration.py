"""Launcher and icon integration on Linux and Windows."""

from __future__ import annotations

import importlib.util
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "linux"
DESKTOP_FILE = INSTALLER / "vardiashift.desktop"
MAKE_ICONS = INSTALLER / "make-icons.py"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
DIB_MAGIC = b"\x28\x00\x00\x00"


def _load_make_icons():
    spec = importlib.util.spec_from_file_location("make_icons", MAKE_ICONS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _desktop_entries() -> dict[str, str]:
    """The stock desktop file, read the way a desktop would."""
    return dict(
        line.split("=", 1)
        for line in DESKTOP_FILE.read_text().splitlines()
        if "=" in line and not line.startswith(("#", ";"))
    )


def _ico_entries(path: Path):
    data = path.read_bytes()
    _reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert kind == 1, "not an icon file"
    offset = 6
    for _ in range(count):
        width, height, _c, _r, planes, bits, size, position = struct.unpack(
            "<BBBBHHII", data[offset : offset + 16]
        )
        offset += 16
        yield (
            width or 256,
            height or 256,
            planes,
            bits,
            data[position : position + size],
        )


# -- the shipped icon --------------------------------------------------------
def test_icon_file_exists():
    assert (ROOT / "assets" / "icon.png").is_file()
    assert (ROOT / "assets" / "icon.ico").is_file()


def test_ico_small_entries_are_bmp_not_png():
    """PyInstaller's resource compiler drops an all-PNG .ico on Windows."""
    entries = list(_ico_entries(ROOT / "assets" / "icon.ico"))
    assert entries, "no icon entries"

    for width, _height, _planes, _bits, blob in entries:
        if width <= 128:
            assert blob[:4] == DIB_MAGIC, f"{width}x{width} entry is not a DIB"


def test_ico_carries_every_size_a_desktop_asks_for():
    sizes = {width for width, _h, _p, _b, _blob in _ico_entries(ROOT / "assets" / "icon.ico")}
    for expected in (16, 32, 48, 64, 128, 256):
        assert expected in sizes


def test_ico_entries_declare_32_bit_colour():
    for width, _height, _planes, bits, _blob in _ico_entries(ROOT / "assets" / "icon.ico"):
        assert bits == 32, f"{width} entry is not 32-bit"


def test_rebuilding_the_icon_is_stable(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location(
            "build_icon", ROOT / "scripts" / "build_icon.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    target = tmp_path / "icon.ico"
    module.build(ROOT / "assets" / "icon.png", target)
    assert target.read_bytes() == (ROOT / "assets" / "icon.ico").read_bytes()


# -- icon sizes --------------------------------------------------------------
def test_make_icons_writes_one_file_per_size(tmp_path):
    module = _load_make_icons()
    written = module.write_icons(ROOT / "assets" / "icon.png", tmp_path)

    assert len(written) == len(module.SIZES)
    for path in written:
        assert path.is_file()
        assert path.read_bytes()[:8] == PNG_MAGIC


def test_generated_icon_has_the_size_its_folder_claims(tmp_path):
    from PIL import Image

    module = _load_make_icons()
    module.write_icons(ROOT / "assets" / "icon.png", tmp_path)
    for size in module.SIZES:
        path = module.icon_folder(tmp_path, size) / "vardiashift.png"
        with Image.open(path) as image:
            assert image.size == (size, size)


# -- desktop entry -----------------------------------------------------------
def test_desktop_file_is_present_and_executable_flagged():
    assert DESKTOP_FILE.is_file()
    assert (INSTALLER / "install.sh").stat().st_mode & 0o111, "install.sh is not executable"


def test_desktop_entry_declares_an_application():
    entries = _desktop_entries()
    assert entries["Type"] == "Application"
    assert entries["Terminal"] == "false"
    assert entries["Name"] == "VardiaShift"


def test_desktop_entry_names_the_icon_and_category():
    entries = _desktop_entries()
    assert entries["Icon"] == "vardiashift"
    assert "Office" in entries["Categories"]


def test_desktop_entry_has_one_main_category():
    """Two main categories make the app appear twice in the menu."""
    entries = _desktop_entries()
    main = [c for c in entries["Categories"].split(";") if c and "/" not in c]
    assert len(main) == 1


def test_desktop_entry_startup_class_matches_the_application():
    from app.main import DESKTOP_FILE_NAME

    entries = _desktop_entries()
    assert entries["StartupWMClass"] == Path(DESKTOP_FILE_NAME).stem


def test_desktop_entry_paths_are_placeholders_until_installed():
    """A bare Exec= would need the folder on PATH; install.sh fills both in."""
    entries = _desktop_entries()
    assert entries["Exec"] == "vardiashift"
    assert entries["Path"] == "VARDIASHIFT_APP_DIR"


# -- install.sh --------------------------------------------------------------
def _install(prefix: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable and "bash", str(INSTALLER / "install.sh"),
         "--prefix", str(prefix), *extra],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


@pytest.fixture
def fake_build(tmp_path):
    """A stand-in for dist/VardiaShift, so the test needs no PyInstaller run."""
    source = tmp_path / "source" / "VardiaShift"
    (source / "_internal" / "assets").mkdir(parents=True)
    binary = source / "VardiaShift"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    (source / "_internal" / "assets" / "icon.png").write_bytes(
        (ROOT / "assets" / "icon.png").read_bytes()
    )
    return source.parent


@pytest.mark.skipif(os.name == "nt", reason="install.sh is a Linux installer")
def test_install_registers_a_desktop_entry_and_icons(tmp_path, fake_build):
    prefix = tmp_path / "prefix"
    result = _install(prefix, "--source", str(fake_build))
    assert result.returncode == 0, result.stderr

    entry = prefix / "applications" / "vardiashift.desktop"
    assert entry.is_file()
    installed = dict(
        line.split("=", 1)
        for line in entry.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    assert installed["Exec"] == str(prefix / "vardiashift" / "VardiaShift")
    assert installed["Path"] == str(prefix / "vardiashift")

    icons = list((prefix / "icons").rglob("vardiashift.png"))
    assert len(icons) >= 8


@pytest.mark.skipif(os.name == "nt", reason="install.sh is a Linux installer")
def test_install_rejects_a_missing_build(tmp_path):
    result = _install(tmp_path, "--source", str(tmp_path / "nowhere"))
    assert result.returncode != 0
    assert "No built application" in result.stdout + result.stderr


@pytest.mark.skipif(os.name == "nt", reason="install.sh is a Linux installer")
def test_uninstall_removes_the_application_and_entry(tmp_path, fake_build):
    prefix = tmp_path / "prefix"
    assert _install(prefix, "--source", str(fake_build)).returncode == 0
    assert _install(prefix, "--uninstall").returncode == 0

    assert not (prefix / "vardiashift").exists()
    assert not (prefix / "applications" / "vardiashift.desktop").exists()
    assert not list((prefix / "icons").rglob("vardiashift.png"))


@pytest.mark.skipif(os.name == "nt", reason="install.sh is a Linux installer")
def test_uninstall_leaves_other_icons_alone(tmp_path, fake_build):
    prefix = tmp_path / "prefix"
    assert _install(prefix, "--source", str(fake_build)).returncode == 0
    other = prefix / "icons" / "hicolor" / "48x48" / "apps" / "otherapp.png"
    other.write_bytes(b"not ours")

    assert _install(prefix, "--uninstall").returncode == 0
    assert other.is_file()


@pytest.mark.skipif(os.name == "nt", reason="install.sh is a Linux installer")
def test_uninstall_on_a_clean_prefix_is_harmless(tmp_path):
    assert _install(tmp_path, "--uninstall").returncode == 0


@pytest.mark.skipif(os.name == "nt", reason="install.sh is a Linux installer")
def test_install_script_is_valid_bash():
    result = subprocess.run(
        ["bash", "-n", str(INSTALLER / "install.sh")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


# -- runtime wiring ----------------------------------------------------------
def test_application_advertises_the_desktop_file(qt_app):
    from app.main import DESKTOP_FILE_NAME

    assert DESKTOP_FILE_NAME == "vardiashift.desktop"


def test_setup_window_gets_an_icon(context, qt_app):
    from app.main import Application
    from app.ui.setup_window import SetupWindow

    controller = Application(context)
    controller.create_qt_app()
    window = SetupWindow(data_directory=str(context.paths.root), version="1.0.0")
    controller._apply_window_icon(window)

    assert window.windowIcon().isNull() is False
    window.deleteLater()


def test_login_window_gets_an_icon(context, qt_app, session):
    from app.main import Application
    from app.ui.login_window import LoginWindow

    controller = Application(context)
    controller.create_qt_app()
    window = LoginWindow(organization=context.organization_name, version="1.0.0")
    controller._apply_window_icon(window)

    assert window.windowIcon().isNull() is False
    window.deleteLater()


def test_main_window_gets_an_icon(context, qt_app, session):
    from app.main import Application
    from app.ui.main_window import MainWindow

    controller = Application(context)
    controller.create_qt_app()
    window = MainWindow(context)
    controller._apply_window_icon(window)

    assert window.windowIcon().isNull() is False
    window.deleteLater()


def test_icon_is_applied_even_without_an_icon_file(context, qt_app, monkeypatch):
    """A missing asset must not raise; the window just keeps the default."""
    from app.main import Application

    controller = Application(context)
    controller._app_icon = None

    from PySide6.QtWidgets import QWidget

    window = QWidget()
    controller._apply_window_icon(window)
    window.deleteLater()


@pytest.fixture
def pretend_windows(monkeypatch):
    """Make the Windows-only branch run on Linux."""

    def apply(shell32):
        module = type("ctypes", (), {"windll": type("w", (), {"shell32": shell32})()})()
        monkeypatch.setitem(sys.modules, "ctypes", module)
        monkeypatch.setattr(os, "name", "nt")

    return apply


def test_windows_app_id_is_declared_before_any_window(pretend_windows):
    """The ID is read when the first window appears, so it must be set first."""
    from app.main import Application

    calls = []

    class Shell32:
        def SetCurrentProcessExplicitAppUserModelID(self, value):
            calls.append(value)

    pretend_windows(Shell32())
    Application._declare_windows_app_id()
    assert calls == ["VardiaShift.Desktop"]


def test_windows_app_id_failure_does_not_stop_startup(pretend_windows):
    from app.main import Application

    class Shell32:
        def SetCurrentProcessExplicitAppUserModelID(self, value):
            raise OSError("no shell32 here")

    pretend_windows(Shell32())
    Application._declare_windows_app_id()


def test_windows_app_id_is_skipped_off_windows(monkeypatch):
    from app.main import Application

    called = []
    monkeypatch.setattr(
        sys, "modules", dict(sys.modules, ctypes=_ExplodingCtypes(called))
    )
    monkeypatch.setattr(os, "name", "posix")

    Application._declare_windows_app_id()
    assert called == []


class _ExplodingCtypes:
    def __init__(self, called):
        self._called = called

    def __getattr__(self, name):
        self._called.append(name)
        raise AssertionError("ctypes must not be touched off Windows")


# -- Windows build inputs ----------------------------------------------------
def test_installer_shortcuts_use_the_embedded_executable_icon():
    """Without IconFilename Inno falls back to a generic icon."""
    text = (ROOT / "installer" / "windows" / "VardiaShift.iss").read_text()
    icons_section = text.split("[Icons]")[1].split("[Tasks]")[0]
    shortcuts = [
        line for line in icons_section.splitlines()
        if line.startswith("Name:") and not line.startswith(";")
    ]
    assert len(shortcuts) == 2
    # Inno Setup falls back to the target's own icon, which is what the spec
    # embeds, so pointing at a bundled .ico path would be wrong as well.
    assert all("IconFilename" not in line for line in shortcuts)


def test_pyinstaller_spec_embeds_the_icon_on_windows_only():
    text = (ROOT / "VardiaShift.spec").read_text()
    assert 'os.name == "nt"' in text
    assert "icon.ico" in text
    assert "icon=exe_icon" in text
