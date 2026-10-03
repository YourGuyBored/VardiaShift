"""Pytest fixtures: every test runs against a throwaway Shiftora database."""

from __future__ import annotations

import os

# Headless by default so GUI tests run on CI servers without a display.
# Contributors with a screen who want to *watch* the windows can override:
#     QT_QPA_PLATFORM=xcb python -m pytest tests/test_ui.py
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import gc
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _qt_ordered_teardown():
    """Deterministically destroy Qt objects before pytest's shutdown GC.

    PySide6 widgets collected *after* QApplication is torn down segfault the
    interpreter (pytest's `pytest_unconfigure` runs a hard `gc.collect()`).
    Closing and deleting every top-level widget while the application object
    is still alive keeps teardown ordered and crash-free.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            for _ in range(3):  # flush queued deleteLater() events
                for widget in app.topLevelWidgets():
                    try:
                        widget.close()
                        widget.deleteLater()
                    except RuntimeError:
                        pass  # C++ object already gone
                try:
                    app.processEvents()
                except RuntimeError:
                    break
    except Exception:
        pass
    gc.collect()


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirect the app data directory so tests never touch a real install."""
    data_dir = tmp_path / "shiftora-data"
    monkeypatch.setenv("SHIFTORA_DATA_DIR", str(data_dir))
    from app.utils import paths as paths_module

    paths_module._cache = None
    yield data_dir
    paths_module._cache = None


@pytest.fixture
def paths(isolated_data_dir):
    from app.utils.paths import app_paths

    return app_paths(refresh=True)


@pytest.fixture
def database(paths):
    from app.database.database import Database

    db = Database(paths=paths)
    yield db
    db.close_all()


@pytest.fixture
def repos(database):
    from app.database.repositories import Repositories

    return Repositories(database)


@pytest.fixture
def context(isolated_data_dir):
    from app.context import ApplicationContext
    from app.utils.paths import AppPaths

    ctx = ApplicationContext(paths=AppPaths(isolated_data_dir).ensure())
    ctx.bootstrap()
    yield ctx
    ctx.shutdown()


@pytest.fixture
def settings(context):
    return context.settings


@pytest.fixture
def auth(context):
    return context.authentication


@pytest.fixture
def employees(context):
    return context.employees


@pytest.fixture
def attendance(context):
    return context.attendance


@pytest.fixture
def admin(context):
    return context.authentication.create_first_admin("admin", "Sup3rSecret!", "Sup3rSecret!", "Test Admin")


@pytest.fixture
def session(context, admin):
    return context.authentication.authenticate("admin", "Sup3rSecret!")


@pytest.fixture
def employee(context, admin):
    return context.employees.create(
        employee_code="EMP-001",
        full_name="Juan Dela Cruz",
        department="IT",
        position="Student Assistant",
        admin_username="admin",
    )


@pytest.fixture
def clock(context):
    return context.clock


class FrozenClock:
    """Test clock pinned to a Monday 10:00 inside the configured work week.

    Using a fixed reference removes any dependency on the real calendar (weekend
    runs, midnight boundaries) so attendance rules are exercised deterministically.
    """

    def __init__(self, context, reference: datetime) -> None:
        self.context = context
        self.reference = reference
        context.attendance.set_now_provider(lambda: self.reference)

    def at(self, hour: int, minute: int = 0, day_offset: int = 0) -> datetime:
        day = self.reference.date() + timedelta(days=day_offset)
        return datetime.combine(day, time(hour=hour, minute=minute))

    def iso(self, hour: int, minute: int = 0, day_offset: int = 0) -> str:
        return self.at(hour, minute, day_offset).strftime("%Y-%m-%dT%H:%M:%S")

    def advance(self, **kwargs) -> "FrozenClock":
        self.reference = self.reference + timedelta(**kwargs)
        return self


@pytest.fixture
def frozen(context):
    clock = context.clock
    monday = clock.week_bounds().start
    reference = datetime.combine(monday, time(hour=10, minute=0))
    return FrozenClock(context, reference)


def at(context, day_offset: int = 0, hour: int = 9, minute: int = 0) -> datetime:
    """A deterministic timestamp relative to the configured week start."""
    clock = context.clock
    base = datetime.combine(
        clock.week_bounds().start, time(hour=hour, minute=minute)
    )
    return base + timedelta(days=day_offset)