"""Render every VardiaShift screen to a PNG so the design can be reviewed.

    QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/shoot_ui.py /tmp/shots

Builds a throwaway database with a week of attendance, then grabs each page as
the user would see it. Screens that need a modal dialog are handled too.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/vardiashift-shots")
DATA = Path("/tmp/vardiashift-shots-data")

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["VARDIASHIFT_DATA_DIR"] = str(DATA)

shutil.rmtree(DATA, ignore_errors=True)
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.constants import APP_VERSION  # noqa: E402
from app.context import ApplicationContext  # noqa: E402
from app.utils.appearance import DEFAULT_ACCENT  # noqa: E402
from app.utils.paths import AppPaths  # noqa: E402

NAMES = [
    ("EMP-001", "Juan Dela Cruz", "Operations", "Supervisor"),
    ("EMP-002", "Ana Rivera", "Operations", "Front Desk"),
    ("EMP-003", "Ben Osei", "Warehouse", "Storeman"),
    ("EMP-004", "Chow Wei Ming", "Accounts", "Clerk"),
    ("EMP-005", "Dilnoza Karimova", "Front Desk", "Receptionist"),
]


def settle(times: int = 4) -> None:
    app = QApplication.instance()
    for _ in range(times):
        app.processEvents()


def _local_timezone() -> str:
    """This machine's IANA zone, so the demo clock reads like a workday.

    VardiaShift defaults to UTC, and a screenshot taken in the evening would
    then show the whole day as a night shift.
    """
    try:
        parts = Path("/etc/localtime").resolve().parts
        if "zoneinfo" in parts:
            return "/".join(parts[parts.index("zoneinfo") + 1:])
    except OSError:  # pragma: no cover - platform dependent
        pass
    return "UTC"


def shoot(widget, name: str, width: int = 0, height: int = 0) -> None:
    if width:
        widget.resize(width, height)
    widget.show()
    settle()
    widget.grab().save(str(OUT / f"{name}.png"))
    print("wrote", OUT / f"{name}.png")


def seed(context) -> None:
    """A week of plausible attendance, ending on today.

    Earlier days are ordinary full shifts. Today is built relative to the
    current clock so nothing is ever recorded in the future: two people are
    still clocked in, two have clocked out, and one has not scanned at all -
    every state the dashboard can show. The range stops at Friday so a weekend
    shot still shows a full week rather than an empty one.
    """
    context.authentication.create_first_admin(
        "admin", "Sup3rSecret!", "Sup3rSecret!", "Ana Rivera"
    )
    context.settings.set("organization_name", "Riverside Trading Post", "admin")
    context.settings.set("weekly_goal_hours", 40, "admin")
    context.settings.set("default_weekly_goal_hours", 40, "admin")
    context.settings.set("timezone", _local_timezone(), "admin")

    clock = context.clock
    monday = clock.week_bounds().start
    today = clock.today()
    now = clock.now()
    span = max(0, min((today - monday).days, 4))
    people = [
        context.employees.create(code, name, dept, role, admin_username="admin")
        for code, name, dept, role in NAMES
    ]

    for offset in range(span + 1):
        day = monday + timedelta(days=offset)
        for index, person in enumerate(people):
            if day == today and index == 4:
                continue  # has not scanned today: the "Not In" row
            if day == today:
                start = max(
                    now - timedelta(hours=6 - (index % 3)),
                    datetime.combine(today, time(0, 5)),
                )
                context.attendance.time_in(person, start)
                out = now - timedelta(minutes=45 + index * 5)
                if index in (1, 3) or out <= start:
                    continue  # still on the clock
                context.attendance.time_out(person, out)
            else:
                in_hour = 8 + (index % 3)
                context.attendance.time_in(
                    person,
                    clock.parse(
                        f"{day.isoformat()}T{in_hour:02d}:{(index * 7) % 60:02d}:00"
                    ),
                )
                context.attendance.time_out(
                    person,
                    clock.parse(
                        f"{day.isoformat()}T{in_hour + 8:02d}:{(index * 11) % 60:02d}:00"
                    ),
                )


def main() -> int:
    app = QApplication(sys.argv)
    from app.ui import theme

    theme.apply_theme(app)

    context = ApplicationContext(paths=AppPaths(DATA).ensure())
    context.bootstrap()
    seed(context)
    context.authentication.authenticate("admin", "Sup3rSecret!")

    from app.main import build_pages
    from app.ui.attendance_kiosk import KioskWindow
    from app.ui.login_window import LoginWindow
    from app.ui.main_window import MainWindow
    from app.ui.setup_window import SetupWindow

    shoot(LoginWindow(organization="Riverside Trading Post", version=APP_VERSION), "01-login")
    shoot(SetupWindow(version=APP_VERSION), "02-setup")

    window = MainWindow(context)
    pages = build_pages(window, context)
    window.resize(1360, 820)
    window.show()
    settle()

    order = [
        ("dashboard", "03-dashboard"),
        ("employees", "04-employees"),
        ("attendance", "05-attendance"),
        ("qr", "06-qr"),
        ("reports", "07-reports"),
        ("settings", "08-settings"),
        ("admin", "09-admin"),
    ]
    for key, name in order:
        window.show_page(key)
        settle()
        pages[key].grab().save(str(OUT / f"{name}.png"))
        print("wrote", OUT / f"{name}.png")

    settings_page = pages["settings"]
    index = next(
        i for i in range(settings_page._tabs.count())
        if settings_page._tabs.tabText(i) == "Appearance"
    )
    settings_page._tabs.setCurrentIndex(index)
    settle()
    settings_page.grab().save(str(OUT / "10-appearance.png"))
    print("wrote", OUT / "10-appearance.png")

    # An accent that is not the default, to prove the palette follows through.
    theme.apply_accent(app, "Orange")
    settle()
    window.show_page("dashboard")
    settle()
    pages["dashboard"].grab().save(str(OUT / "11-dashboard-orange.png"))
    window.grab().save(str(OUT / "12-shell-orange.png"))

    # Back to the default so every README shot shares one palette.
    theme.apply_accent(app, DEFAULT_ACCENT)
    settle()

    kiosk = KioskWindow(context)
    kiosk.show_kiosk()
    settle()
    kiosk.grab().save(str(OUT / "13-kiosk.png"))
    print("wrote", OUT / "13-kiosk.png")

    window.close()
    kiosk.force_close()
    context.shutdown()
    print(f"\nAll shots in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())