"""Tests for the commit helpers: the pre-commit guard and the one-click task.

The guard is the last thing standing between a real attendance database or a
service-account key and a public GitHub repository, so its refusals are
pinned here. These tests never touch the real repository: they exercise the
pure helpers and run the CLI against a throwaway ``git init`` sandbox.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    """Import a script from scripts/ without needing it on sys.path."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load("shiftora_precommit_check", "precommit_check.py")


@pytest.fixture(scope="module")
def commit_helper():
    return _load("shiftora_one_click_commit", "one_click_commit.py")


# -- banned paths ------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        "attendance.db",
        "shiftora.db-wal",
        "shiftora.db-shm",
        "data/backup.db",
        "secrets.env",
        "server.pem",
        "tls.key",
        "cert.p12",
        "id_rsa",
        ".venv/bin/python",
        "__pycache__/mod.pyc",
        "dist/Shiftora/Shiftora",
        "build/lib/app.py",
    ],
)
def test_guard_blocks_dangerous_paths(guard, path):
    assert guard.is_banned(path) is not None


@pytest.mark.parametrize(
    "path",
    [
        "app/main.py",
        "tests/test_ui.py",
        "CHANGELOG.md",
        "README.md",
        "app/ui/window_sizing.py",
        "scripts/one_click_commit.py",
        "installer/windows/Shiftora.iss",
    ],
)
def test_guard_allows_normal_source_files(guard, path):
    assert guard.is_banned(path) is None


# -- secret shapes -----------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("K='-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----'", "private key"),
        ("K='AIza" + "A" * 35 + "'", "Google API key"),
        ("K='ghp_" + "a" * 36 + "'", "GitHub token"),
        ("K='AKIA" + "A" * 16 + "'", "AWS access key id"),
        ("K='xoxb-1234567890-abcdef'", "Slack token"),
        ("DSN='postgresql://user:pw@host/db'", "connection string"),
    ],
)
def test_guard_recognises_secret_shapes(guard, text, expected, tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    (tmp_path / "leak.py").write_text(text, encoding="utf-8")
    found = guard.scan_secrets(["leak.py"])
    assert found, f"expected {expected} to be detected"
    assert any(expected in description for _, description in found)


def test_guard_ignores_ordinary_code(guard, tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    (tmp_path / "fine.py").write_text(
        'import os\nURL = "http://192.168.1.5:8123/c/abc"\nN = 42\n', encoding="utf-8"
    )
    assert guard.scan_secrets(["fine.py"]) == []


def test_guard_ignores_short_strings_that_look_alike(guard, tmp_path, monkeypatch):
    """A bare identifier or a short hash must not trip the guard."""
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    (tmp_path / "ok.py").write_text(
        'H = "AKIA"\nTOKEN = "ghp_short"\nKEY = "AIza"\n', encoding="utf-8"
    )
    assert guard.scan_secrets(["ok.py"]) == []


# -- the test-fixture exemption ----------------------------------------------
@pytest.mark.parametrize(
    "path,exempt",
    [
        ("tests/test_sheets.py", True),
        ("tests/conftest.py", True),
        ("tests/test_ui.py", True),
        ("test_top.py", True),
        ("thing_test.py", True),
        ("app/services/google_sheets.py", False),
        ("README.md", False),
    ],
)
def test_secret_exemption_covers_tests_only(guard, path, exempt):
    assert guard.is_secret_exempt(path) is exempt


def test_real_repo_has_no_committable_secrets(guard):
    """The actual working tree must pass the guard it ships with."""
    files = guard.staged_files()
    assert guard.scan_secrets(files) == []
    assert [(p, guard.is_banned(p)) for p in files if guard.is_banned(p)] == []


# -- CLI behaviour in a sandbox ---------------------------------------------
def _sandbox(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    (repo / ".gitignore").write_text("__pycache__/\n")
    for script in ("one_click_commit.py", "precommit_check.py"):
        (repo / "scripts").mkdir(exist_ok=True)
        (repo / "scripts" / script).write_text(
            (ROOT / "scripts" / script).read_text(encoding="utf-8"), encoding="utf-8"
        )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=repo,
        check=True,
    )
    return repo


def test_guard_cli_blocks_a_database(tmp_path):
    repo = _sandbox(tmp_path)
    (repo / "attendance.db").write_text("real employee data")
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "precommit_check.py")],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "attendance.db" in result.stdout


def test_guard_cli_passes_on_a_clean_tree(tmp_path):
    repo = _sandbox(tmp_path)
    (repo / "notes.md").write_text("hello")
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "precommit_check.py")],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_helper_runs_tests_before_staging_anything(tmp_path):
    repo = _sandbox(tmp_path)
    (repo / "tests" / "test_bad.py").write_text("def test_bad():\n    assert False\n")
    (repo / "notes.md").write_text("hello")
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "one_click_commit.py"), "-m", "should not commit"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Tests FAILED" in result.stdout
    assert "should not commit" not in result.stdout
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "should not commit" not in log


def test_helper_refuses_when_the_guard_blocks(tmp_path):
    repo = _sandbox(tmp_path)
    (repo / "attendance.db").write_text("real employee data")
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "one_click_commit.py"), "-m", "leak"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Pre-commit check FAILED" in result.stdout
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "leak" not in log


def test_helper_commits_when_all_is_clean(tmp_path):
    repo = _sandbox(tmp_path)
    (repo / "notes.md").write_text("hello")
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "one_click_commit.py"), "-m", "add notes"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "add notes" in log


def test_helper_never_pushes():
    """A commit helper that pushes would publish unreviewed work."""
    source = (ROOT / "scripts" / "one_click_commit.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert '"push"' not in code
    assert "'push'" not in code
    assert "git push" not in code


def test_helper_finds_the_project_venv(commit_helper):
    """It must locate the repo's own pytest, not rely on an activated shell."""
    command = commit_helper.find_pytest()
    assert command
    assert any("pytest" in part for part in command)


def test_helper_falls_back_when_no_venv(commit_helper, tmp_path, monkeypatch):
    monkeypatch.setattr(commit_helper, "ROOT", tmp_path)
    monkeypatch.setitem(sys.modules, "pytest", None)
    monkeypatch.setattr(commit_helper.shutil, "which", lambda name: None)
    command = commit_helper.find_pytest()
    assert command[-2:] == ["-m", "pytest"]