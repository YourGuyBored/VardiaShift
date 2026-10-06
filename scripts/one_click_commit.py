#!/usr/bin/env python3
"""One-click commit helper for Shiftora (run from VS Code: Tasks → Run Task, or terminal).

1. Runs the full test suite. Stops immediately if anything fails.
2. Runs ``scripts/precommit_check.py``, which refuses to continue if a
   secret, database or build artefact would be committed.
3. Stages everything (``git add -A``).
4. Takes a commit message (from CLI arguments or interactive prompt) and commits.

It never pushes. Push from the VS Code task "Git: push to origin", from
Source Control, or from the terminal when ready.

Portable by design: standard library only, automatically detects the project's
virtual environment (.venv) or system Python, and runs seamlessly on Windows,
macOS, and Linux.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> int:
    try:
        completed = subprocess.run(list(args), cwd=ROOT)
    except FileNotFoundError as exc:
        print(f"Cannot run {args[0]}: {exc}")
        print("Is it installed and on PATH?")
        return 127
    return completed.returncode


def find_pytest() -> list[str]:
    """Find a usable pytest command.

    Prefers the project's local virtual environment (.venv) so that running this
    script from any shell or system Python still finds all installed dependencies.
    """
    venv = ROOT / ".venv"
    if venv.is_dir():
        # Linux / macOS virtualenv pytest binary
        pytest_bin = venv / "bin" / "pytest"
        if pytest_bin.is_file():
            return [str(pytest_bin)]

        # Windows virtualenv pytest binary
        pytest_exe = venv / "Scripts" / "pytest.exe"
        if pytest_exe.is_file():
            return [str(pytest_exe)]

        # Virtualenv python binary
        py_bin = venv / "bin" / "python"
        if py_bin.is_file():
            return [str(py_bin), "-m", "pytest"]

        py_exe = venv / "Scripts" / "python.exe"
        if py_exe.is_file():
            return [str(py_exe), "-m", "pytest"]

    # Current python environment if pytest is importable
    try:
        import pytest  # noqa: F401
        return [sys.executable, "-m", "pytest"]
    except ImportError:
        pass

    # Check system PATH
    which_pytest = shutil.which("pytest")
    if which_pytest:
        return [which_pytest]

    return [sys.executable, "-m", "pytest"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Shiftora commit helper: run tests, stage changes, and commit.",
    )
    parser.add_argument(
        "-m",
        "--message",
        dest="message",
        help="Commit message. If omitted, prompts interactively.",
        default="",
    )
    parser.add_argument(
        "positional_message",
        nargs="*",
        help="Optional commit message passed as positional arguments.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if run("git", "rev-parse", "--is-inside-work-tree") != 0:
        print("Not inside a git repository. Nothing to do.")
        return 1

    pytest_cmd = find_pytest()
    print("Step 1/4: running the test suite...")
    test_args = pytest_cmd + ["tests/", "-q"]
    if run(*test_args) != 0:
        print("Tests FAILED. Nothing was staged and nothing was committed.")
        return 1

    print("Step 2/4: checking for secrets, databases and junk...")
    if run(sys.executable, str(ROOT / "scripts" / "precommit_check.py")) != 0:
        print("Pre-commit check FAILED. Nothing was staged and nothing was committed.")
        return 1

    print("Step 3/4: staging all changes...")
    if run("git", "add", "-A") != 0:
        print("Could not stage changes. Nothing was committed.")
        return 1

    message = (args.message or " ".join(args.positional_message)).strip()
    if not message:
        print("Step 4/4: commit message (Ctrl+C aborts, nothing is committed).")
        try:
            while not message:
                message = input("Commit message: ").strip()
                if not message:
                    print("A message is required.")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted. Staged changes were left in place.")
            return 130
    else:
        print(f"Step 4/4: committing with message: {message!r}")

    if run("git", "commit", "-m", message) != 0:
        print("Commit failed. Staged changes were left in place.")
        return 1

    print("Committed successfully. Nothing was pushed — push from Source Control when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
