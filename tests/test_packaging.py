"""Checks that keep the PyInstaller bundle in step with lazy imports.

Most admin pages are imported by name when the administrator first opens
them. PyInstaller cannot follow that import, so the module has to be listed
in ``VardiaShift.spec``. A source checkout works either way; the packaged
app is the one that raises ``ModuleNotFoundError`` when the page is opened.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.main import LAZY_PAGE_MODULES

ROOT = Path(__file__).resolve().parents[1]


def _hidden_imports() -> set[str]:
    """The string entries in the spec's ``Analysis(hiddenimports=...)`` list."""
    tree = ast.parse((ROOT / "VardiaShift.spec").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Analysis"
        ):
            for keyword in node.keywords:
                if keyword.arg == "hiddenimports":
                    return {
                        element.value
                        for element in keyword.value.elts
                        if isinstance(element, ast.Constant)
                        and isinstance(element.value, str)
                    }
    raise AssertionError("VardiaShift.spec has no Analysis(hiddenimports=...) list")


def test_spec_bundles_every_lazily_loaded_page():
    missing = sorted(set(LAZY_PAGE_MODULES) - _hidden_imports())
    assert not missing, (
        "VardiaShift.spec must list every module in app.main.LAZY_PAGE_MODULES. "
        f"Missing: {', '.join(missing)}"
    )


def test_lazy_page_modules_import_cleanly():
    import importlib

    for module_name in LAZY_PAGE_MODULES:
        assert importlib.import_module(module_name).__name__ == module_name


def test_bundle_checker_finds_the_page_modules(tmp_path):
    from scripts import check_bundle

    binary = tmp_path / "VardiaShift"
    binary.write_bytes(
        b"header" + b"".join(module.encode("utf-8") for module in LAZY_PAGE_MODULES)
    )
    assert check_bundle.main(["check_bundle.py", str(tmp_path)]) == 0


def test_bundle_checker_reports_a_missing_page(tmp_path):
    from scripts import check_bundle

    binary = tmp_path / "VardiaShift"
    binary.write_bytes(b"header")
    assert check_bundle.main(["check_bundle.py", str(tmp_path)]) == 1
