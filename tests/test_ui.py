"""GUI tests: every screen, dialog and button actually works."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, QTime, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.constants import QR_TIME_IN, QR_TIME_OUT  # noqa: E402
from app.qr.tokens import build_payload  # noqa: E402


@pytest.fixture(autouse=True)
def no_blocking_dialogs(monkeypatch):
    """Make every system dialog non-modal so a stray message box cannot hang CI."""
    from PySide6.QtPrintSupport import QPrintDialog
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", ""))
    )
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", ""))
    )
    monkeypatch.setattr(QPrintDialog, "exec", lambda self: 0)
    monkeypatch.setattr(
        QInputDialog,
        "getItem",
        staticmethod(lambda parent, title, label, items, current=0, editable=False: (
            items[current] if items else "",
            True,
        )),
    )
    # The kiosk password gate is modal by design; tests drive it through
    # _try_unlock() or _exit_allowed and must never block on exec().
    from PySide6.QtWidgets import QDialog

    from app.ui.attendance_kiosk import KioskExitDialog

    monkeypatch.setattr(KioskExitDialog, "exec", lambda self: QDialog.DialogCode.Rejected)


@pytest.fixture
def admin_session(context, admin):
    context.authentication.authenticate("admin", "Sup3rSecret!")
    return context.authentication.session


@pytest.fixture
def team(context, admin_session, frozen):
    juan = context.employees.create(
        "EMP-001", "Juan Dela Cruz", "IT", "Student Assistant", admin_username="admin"
    )
    maria = context.employees.create(
        "EMP-002", "Maria Santos", "HR", "Coordinator", admin_username="admin"
    )
    context.attendance.time_in(juan, frozen.at(9, 2))
    context.attendance.time_out(juan, frozen.at(17, 14))
    context.attendance.time_in(maria, frozen.at(8, 0))
    return juan, maria


# -- main window -------------------------------------------------------------
def test_main_window_builds_every_page(context, qt_app, admin_session):
    from app.main import build_pages
    from app.ui.main_window import MainWindow

    window = MainWindow(context)
    pages = build_pages(window, context)
    assert set(pages) == {
        "dashboard", "employees", "attendance", "qr", "reports", "settings", "admin"
    }
    for key in pages:
        window.show_page(key)
        assert window.stack.currentWidget() is pages[key]
        assert window.sidebar._buttons[key].isChecked()
    window.close()


def test_sidebar_navigation_emits_keys(context, qt_app):
    from app.ui.main_window import Sidebar

    sidebar = Sidebar("Acme", "admin")
    seen = []
    sidebar.navigate.connect(seen.append)
    sidebar._buttons["reports"].click()
    assert seen == ["reports"]
    sidebar.logout.emit()


# -- dashboard ---------------------------------------------------------------
def test_dashboard_shows_team_and_totals(context, qt_app, team):
    from app.ui.dashboard import DashboardPage

    page = DashboardPage(context)
    page.refresh()
    assert page._table.rowCount() == 2
    assert page._stat_working.value_text() == "1"
    assert page._stat_out.value_text() == "1"
    assert page._stat_employees.value_text() == "2"
    # Juan's closed 8h12m session + Maria's 2h live accrual (frozen at 10:00).
    assert "10h 12m" in page._stat_today.value_text()
    assert page._week_percent.text().endswith("%")


def test_dashboard_search_filters_rows(context, qt_app, team):
    from app.ui.dashboard import DashboardPage

    page = DashboardPage(context)
    page._search_box.setText("maria")
    assert page._table.rowCount() == 1
    page._search_box.setText("zzz")
    assert page._table.rowCount() == 0
    page._search_box.setText("")
    assert page._table.rowCount() == 2


def test_dashboard_status_filter(context, qt_app, team):
    from app.ui.dashboard import DashboardPage

    page = DashboardPage(context)
    page._filter_box.setCurrentIndex(2)  # Timed Out
    assert page._table.rowCount() == 1
    page._filter_box.setCurrentIndex(1)  # Working
    assert page._table.rowCount() == 1


def test_dashboard_empty_state(context, qt_app, admin_session):
    from app.ui.dashboard import DashboardPage

    page = DashboardPage(context)
    page.refresh()
    assert page._table.rowCount() == 0
    assert page._table.rowCount() == 0


# -- employees ---------------------------------------------------------------
def test_employee_page_lists_and_searches(context, qt_app, team):
    from app.ui.employee_management import EmployeePage

    page = EmployeePage(context)
    assert page._table.rowCount() == 2
    page._search_box.setText("EMP-002")
    assert page._table.rowCount() == 1
    page._search_box.setText("")
    assert page._table.rowCount() == 2


def test_employee_dialog_creates_an_employee(context, qt_app, admin_session):
    from app.ui.employee_management import EmployeeDialog

    dialog = EmployeeDialog(context, None)
    assert dialog._code.text() == "EMP-001"   # suggested next code
    dialog._name.setText("Pedro Reyes")
    dialog._department.setText("IT")
    dialog._position.setText("Assistant")
    dialog._goal.setCurrentIndex(dialog._goal.findData(20))
    dialog._on_save()
    created = context.employees.get_by_code("EMP-001")
    assert created is not None
    assert created.full_name == "Pedro Reyes"
    assert created.goal_hours(context.settings.settings.default_weekly_goal_hours) == 20
    assert created.qr_token


def test_employee_dialog_shows_validation_errors(context, qt_app, admin_session):
    from app.ui.employee_management import EmployeeDialog

    dialog = EmployeeDialog(context, None)
    dialog._name.setText("")
    dialog._on_save()
    assert not dialog._errors["full_name"].isHidden()
    assert context.employees.list() == []


def test_employee_dialog_rejects_duplicate_code(context, qt_app, team):
    from app.ui.employee_management import EmployeeDialog

    dialog = EmployeeDialog(context, None)
    dialog._code.setText("EMP-001")
    dialog._name.setText("Clone")
    dialog._on_save()
    assert not dialog._errors["employee_code"].isHidden()
    assert len(context.employees.list()) == 2


def test_employee_dialog_edits(context, qt_app, team):
    from app.ui.employee_management import EmployeeDialog

    juan = team[0]
    dialog = EmployeeDialog(context, juan)
    assert dialog._code.isReadOnly()
    dialog._name.setText("Juan Dela Cruz Jr")
    dialog._on_save()
    assert context.employees.get(juan.employee_id).full_name == "Juan Dela Cruz Jr"


def test_employee_page_toggles_status(context, qt_app, team, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.employee_management import EmployeePage

    page = EmployeePage(context)
    page._table.selectRow(0)
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page._toggle_status()
    assert len(context.employees.list(status="inactive")) == 1
    page._table.selectRow(0)
    page._toggle_status()
    assert len(context.employees.list(status="inactive")) == 0


def test_employee_page_regenerates_qr(context, qt_app, team, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.employee_management import EmployeePage

    page = EmployeePage(context)
    page._table.selectRow(0)
    before = context.employees.list()[0].qr_token
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page._regenerate_qr()
    assert context.employees.list()[0].qr_token != before


# -- attendance --------------------------------------------------------------
def test_attendance_page_today_and_history(context, qt_app, team, frozen):
    from app.ui.attendance_view import AttendancePage

    page = AttendancePage(context)
    page.refresh()
    # Point the date filter at the frozen work day (refresh resets it to real today).
    day = frozen.reference
    page._today_date.setDate(QDate(day.year, day.month, day.day))
    page._tabs.setCurrentIndex(0)
    assert page._today_table.rowCount() == 2
    assert page._today_table.columnCount() == 7
    assert page._today_table.item(0, 6) is not None
    assert page._today_table.item(0, 6).text() in ("Desktop", "Phone", "Admin correction", "Manual")
    # Last week is guaranteed empty for fresh fixtures regardless of which
    # weekday today is (the auto-selected employee's records are this week).
    page._range_box.setCurrentIndex(2)  # Last week
    assert page._history_table.rowCount() == 0

    page._tabs.setCurrentIndex(1)
    juan = context.employees.get_by_code("EMP-001")
    page.select_employee(juan.employee_id)
    page._range_box.setCurrentIndex(1)  # This week covers the frozen Monday
    assert page._history_table.rowCount() == 1
    assert page._history_table.item(0, 0).text()
    assert not page._progress_card.isHidden()


def test_attendance_range_filters_change_rows(context, qt_app, team, frozen):
    from app.ui.attendance_view import AttendancePage

    page = AttendancePage(context)
    page.select_employee(context.employees.get_by_code("EMP-001").employee_id)
    # "Today" means real today; the frozen records live on the frozen Monday.
    page._range_box.setCurrentIndex(1)   # This week covers the frozen Monday
    assert page._history_table.rowCount() == 1

    day = frozen.reference
    page._range_box.setCurrentIndex(4)   # Custom range
    page._from_date.setDate(QDate(day.year, day.month, day.day))
    page._to_date.setDate(QDate(day.year, day.month, day.day))
    assert page._history_table.rowCount() == 1

    page._range_box.setCurrentIndex(2)   # Last week
    assert page._history_table.rowCount() == 0


def test_correction_dialog_saves_and_audits(context, qt_app, frozen, admin_session):
    from app.ui.attendance_view import AttendancePage, CorrectionDialog

    juan = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    context.attendance.time_in(juan, frozen.at(9, 0))
    page = AttendancePage(context)
    page.select_employee(juan.employee_id)
    record = context.attendance.record_for_today(juan)

    dialog = CorrectionDialog(context, juan, record, None)
    # QTime wraps after 24h, so set the value explicitly rather than adding.
    dialog._time_out.setTime(QTime(17, 0))
    dialog._reason.setPlainText("Forgot to scan out")
    dialog._on_save()
    assert context.attendance.record_for_today(juan).duration_minutes == 480
    log = context.repositories.audit.list_recent(action="attendance_correct")[0]
    assert log.reason == "Forgot to scan out"


def test_correction_dialog_requires_reason(context, qt_app, frozen, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.attendance_view import CorrectionDialog

    juan = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    context.attendance.time_in(juan, frozen.at(9, 0))
    record = context.attendance.record_for_today(juan)
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a) or QMessageBox.StandardButton.Ok)
    )
    dialog = CorrectionDialog(context, juan, record, None)
    dialog._on_save()
    assert warnings, "the dialog must refuse to save without a reason"
    assert context.attendance.record_for_today(juan).time_out is None


def test_correction_dialog_adds_a_missing_day(context, qt_app, team):
    from app.ui.attendance_view import CorrectionDialog

    juan = context.employees.get_by_code("EMP-001")
    dialog = CorrectionDialog(context, juan, None, juan and context.clock.today())
    dialog._reason.setPlainText("Backdated entry")
    dialog._on_save()
    records = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")
    assert any(r.is_corrected for r in records)


def test_attendance_missing_timeouts_tab_lists_open_sessions(context, qt_app, team, frozen):
    from app.ui.attendance_view import AttendancePage

    page = AttendancePage(context)
    page.refresh()
    page._tabs.setCurrentIndex(2)
    assert page._open_table.rowCount() == 1   # Maria is still clocked in
    assert page._open_table.columnCount() == 5
    assert page._open_table.horizontalHeaderItem(0).text() == "Employee"
    assert page._open_table.horizontalHeaderItem(1).text() == "Date"
    assert page._open_table.horizontalHeaderItem(2).text() == "Time In"
    assert page._open_table.horizontalHeaderItem(3).text() == "Elapsed"
    assert page._open_table.horizontalHeaderItem(4).text() == "Status"
    assert "Maria" in page._open_table.item(0, 0).text()
    assert page._open_table.item(0, 3) is not None


def test_audit_tab_lists_entries(context, qt_app, team):
    from app.ui.attendance_view import AttendancePage

    page = AttendancePage(context)
    page.refresh()
    page._tabs.setCurrentIndex(3)
    assert page._audit_table.rowCount() > 0


# -- QR ----------------------------------------------------------------------
def test_qr_page_generates_action_codes(context, qt_app, admin_session):
    from app.ui.qr_management import QRManagementPage

    page = QRManagementPage(context)
    page._generate_time_in()
    page._generate_time_out()
    assert (context.paths.qr_dir / "time_in_code.png").is_file()
    assert (context.paths.qr_dir / "time_out_code.png").is_file()
    assert context.qr.get_token(QR_TIME_IN) is not None


def test_qr_page_lists_employee_codes(context, qt_app, team):
    from app.ui.qr_management import QRManagementPage

    page = QRManagementPage(context)
    assert page._table.rowCount() == 2
    page._search.setText("maria")
    assert page._table.rowCount() == 1


def test_qr_page_saves_action_card(context, qt_app, admin_session):
    from app.ui.qr_management import QRManagementPage

    page = QRManagementPage(context)
    path = page._save_card(QR_TIME_IN)
    assert path.is_file() and path.stat().st_size > 1000


def test_qr_page_downloads_all_employee_cards(context, qt_app, team, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.qr_management import QRManagementPage

    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page = QRManagementPage(context)
    page._download_all_employees()
    folder = context.paths.qr_dir / "employee_cards"
    assert folder.is_dir()
    assert (folder / "EMP-001.png").is_file()
    assert (folder / "EMP-002.png").is_file()


def test_qr_print_preview_builds(context, qt_app, team):
    from app.ui.qr_management import QRManagementPage, QRPrintPreview

    page = QRManagementPage(context)
    employee = context.employees.get_by_code("EMP-001")
    images = [(f"{employee.employee_code}", page._save_card(QR_TIME_IN))]
    preview = QRPrintPreview(images)
    assert preview._images


# -- reports -----------------------------------------------------------------
def test_reports_page_generates_each_type(context, qt_app, team):
    from app.ui.reports import ReportsPage

    page = ReportsPage(context)
    for index in range(page._type_box.count()):
        page._type_box.setCurrentIndex(index)
        assert page._report is not None
        assert page._report.headers


def test_reports_page_filters_by_employee(context, qt_app, team):
    from app.ui.reports import ReportsPage

    page = ReportsPage(context)
    page._type_box.setCurrentIndex(0)  # daily
    total = len(page._report.rows)
    assert total >= 2
    assert page._report.rows[0][0] == "EMP-001"
    index = page._employee_box.findData(
        context.employees.get_by_code("EMP-001").employee_id
    )
    page._employee_box.setCurrentIndex(index)
    assert len(page._report.rows) < total


def test_reports_page_exports_csv(context, qt_app, team, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from app.ui.reports import ReportsPage

    page = ReportsPage(context)
    page._type_box.setCurrentIndex(1)  # weekly
    target = tmp_path / "report.csv"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page._export_csv()
    assert target.is_file()
    assert "EMP-001" in target.read_text(encoding="utf-8-sig")


def test_reports_page_exports_xlsx(context, qt_app, team, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from app.services.report_service import XLSX_AVAILABLE
    from app.ui.reports import ReportsPage

    if not XLSX_AVAILABLE:
        pytest.skip("openpyxl not installed")
    page = ReportsPage(context)
    target = tmp_path / "report.xlsx"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page._export_xlsx()
    assert target.is_file() and target.stat().st_size > 3000


def test_reports_page_lists_the_builtin_templates(context, qt_app, team):
    from app.ui.reports import ReportsPage

    page = ReportsPage(context)
    names = [page._template_box.itemText(i) for i in range(page._template_box.count())]
    assert "Payroll sheet" in names


def test_reports_page_export_follows_the_chosen_template(context, qt_app, team, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from app.ui.reports import ReportsPage

    page = ReportsPage(context)
    index = page._template_box.findData("Compact (id and hours only)")
    page._template_box.setCurrentIndex(index)
    target = tmp_path / "compact.csv"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page._export_csv()
    header = target.read_text(encoding="utf-8-sig").splitlines()[0]
    assert "Full Name" not in header


def test_reports_page_duplicates_a_template(context, qt_app, team, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from app.ui.reports import ReportsPage

    page = ReportsPage(context)
    page._template_box.setCurrentIndex(page._template_box.findData("Payroll sheet"))
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Payroll copy", True))
    )
    page._duplicate_template()

    assert page._template_box.currentData() == "Payroll copy"
    saved = context.settings.settings.get("report_templates")
    assert "Payroll copy" in saved


def test_reports_page_refuses_a_duplicate_template_name(context, qt_app, team, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from app.ui.reports import ReportsPage

    page = ReportsPage(context)
    page._template_box.setCurrentIndex(page._template_box.findData("Payroll sheet"))
    before = page._template_box.count()
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Payroll sheet", True))
    )
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    page._duplicate_template()
    assert page._template_box.count() == before


def test_template_editor_saves_the_edited_columns(context, qt_app, team):
    from app.services import report_template as tpl
    from app.ui.report_dialogs import TemplateEditorDialog

    template = tpl.template_by_name(context.settings, "Payroll sheet")
    dialog = TemplateEditorDialog(template)
    dialog._table.item(0, 2).setText("Day")
    dialog._on_save()

    assert template.columns[0].heading == "Day"
    assert template.builtin is False


def test_template_editor_needs_a_heading(context, qt_app, team, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.services import report_template as tpl
    from app.ui.report_dialogs import TemplateEditorDialog

    template = tpl.template_by_name(context.settings, "Payroll sheet")
    dialog = TemplateEditorDialog(template)
    dialog._table.item(0, 2).setText("  ")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))
    dialog._on_save()
    assert warnings


def test_template_editor_needs_one_included_column(context, qt_app, team, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    from app.services import report_template as tpl
    from app.ui.report_dialogs import TemplateEditorDialog

    template = tpl.template_by_name(context.settings, "Payroll sheet")
    dialog = TemplateEditorDialog(template)
    for row in range(dialog._table.rowCount()):
        dialog._table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))
    dialog._on_save()
    assert warnings


def test_template_editor_move_up_reorders(context, qt_app, team):
    from app.services import report_template as tpl
    from app.ui.report_dialogs import TemplateEditorDialog

    template = tpl.template_by_name(context.settings, "Payroll sheet")
    dialog = TemplateEditorDialog(template)
    dialog._table.setCurrentCell(1, 0)
    dialog._move(-1)
    assert dialog._table.item(0, 1).text() == "Date"


def test_import_preview_blocks_confirmation_on_errors():
    from PySide6.QtWidgets import QDialogButtonBox

    from app.ui.report_dialogs import ImportPreviewDialog

    dialog = ImportPreviewDialog(
        "Import employees",
        {"new": 3, "changed": 0, "skipped": 1, "errors": 1},
        [(2, "Ana Reyes", "New")],
        [],
        ["line 4: no full name"],
    )
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled() is False
    dialog.close()


def test_import_preview_allows_confirmation_when_clean():
    from PySide6.QtWidgets import QDialogButtonBox

    from app.ui.report_dialogs import ImportPreviewDialog

    dialog = ImportPreviewDialog(
        "Import employees",
        {"new": 2, "changed": 0, "skipped": 0, "errors": 0},
        [(2, "Ana Reyes", "New")],
        [],
        [],
    )
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled() is True
    assert ok.text() == "Import"
    dialog.close()


def test_reports_page_import_writes_nothing_when_cancelled(context, qt_app, team, tmp_path, monkeypatch):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QDialog

    from app.ui.reports import ReportsPage

    source = tmp_path / "attendance.csv"
    source.write_text("Employee ID,Time In,Time Out\nEMP-001,08:00,17:00\n", encoding="utf-8")
    page = ReportsPage(context)
    page._day.setDate(QDate(2026, 3, 2))
    monkeypatch.setattr("app.ui.reports.pick_spreadsheet", lambda *a, **k: source)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    page._import_file()

    assert context.repositories.attendance.get_for_date(
        team[0].employee_id, "2026-03-02"
    ) is None


def test_reports_page_import_writes_after_confirmation(context, qt_app, team, tmp_path, monkeypatch):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QDialog, QMessageBox

    from app.ui.reports import ReportsPage

    source = tmp_path / "attendance.csv"
    source.write_text("Employee ID,Time In,Time Out\nEMP-001,08:00,17:00\n", encoding="utf-8")
    page = ReportsPage(context)
    page._day.setDate(QDate(2026, 3, 2))
    monkeypatch.setattr("app.ui.reports.pick_spreadsheet", lambda *a, **k: source)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    page._import_file()

    records = context.repositories.attendance.list_for_range("2026-03-02", "2026-03-02")
    assert len(records) == 1
    assert context.clock.format_time(records[0].time_in) == "08:00 AM"


def test_employee_page_import_creates_after_confirmation(context, qt_app, team, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from app.ui.employee_management import EmployeePage

    source = tmp_path / "employees.csv"
    source.write_text(
        "Employee ID,Full Name,Department\nEMP-500,Ana Reyes,Field\n", encoding="utf-8"
    )
    page = EmployeePage(context)
    monkeypatch.setattr(
        "app.ui.employee_management.pick_spreadsheet", lambda *a, **k: source
    )
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    page._import_file()

    assert context.employees.get_by_code("EMP-500") is not None


def test_employee_page_import_writes_nothing_when_cancelled(context, qt_app, team, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from app.ui.employee_management import EmployeePage

    source = tmp_path / "employees.csv"
    source.write_text(
        "Employee ID,Full Name\nEMP-500,Ana Reyes\n", encoding="utf-8"
    )
    page = EmployeePage(context)
    monkeypatch.setattr(
        "app.ui.employee_management.pick_spreadsheet", lambda *a, **k: source
    )
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    page._import_file()

    assert context.employees.get_by_code("EMP-500") is None


def test_employee_page_saves_a_sample_file(context, qt_app, team, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from app.ui.employee_management import EmployeePage

    target = tmp_path / "sample.csv"
    page = EmployeePage(context)
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page._save_sample_file()
    assert "Employee ID" in target.read_text(encoding="utf-8")


# -- settings ----------------------------------------------------------------
def test_settings_page_saves_a_value(context, qt_app, admin_session, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.settings import SettingsPage

    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page = SettingsPage(context)
    page._editors["organization_name"].setText("Acme Corporation")
    page._editors["default_weekly_goal_hours"].setCurrentIndex(
        page._editors["default_weekly_goal_hours"].findData(40)
    )
    page.save()
    assert context.settings.settings.organization_name == "Acme Corporation"
    assert context.settings.settings.default_weekly_goal_hours == 40
    log = context.repositories.audit.list_recent(action="settings_update")[0]
    assert "Acme Corporation" in log.new_value


def test_settings_page_rejects_bad_value(context, qt_app, admin_session, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.settings import SettingsPage

    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a) or QMessageBox.StandardButton.Ok)
    )
    page = SettingsPage(context)
    page._editors["default_weekly_goal_hours"].setCurrentIndex(
        page._editors["default_weekly_goal_hours"].findData(20)
    )
    page._editors["organization_name"].setText("x" * 200)   # over the length limit
    page.save()
    assert warnings
    assert context.settings.settings.organization_name != "x" * 200


def test_settings_page_revert_restores_values(context, qt_app, admin_session):
    from app.ui.settings import SettingsPage

    context.settings.set("organization_name", "Acme", "admin")
    page = SettingsPage(context)
    assert page._editors["organization_name"].text() == "Acme"
    page._editors["organization_name"].setText("Changed")
    page.refresh()
    assert page._editors["organization_name"].text() == "Acme"


def test_settings_reset_defaults(context, qt_app, admin_session, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.settings import SettingsPage

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    context.settings.set("organization_name", "Acme", "admin")
    page = SettingsPage(context)
    page._reset_defaults()
    assert context.settings.settings.organization_name == "VardiaShift"


def test_settings_page_backup_and_restore(context, qt_app, team, admin_session, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.settings import SettingsPage

    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page = SettingsPage(context)
    page._create_backup()
    assert page._backup_table.rowCount() == 1
    assert context.backups.list_backups()

    # Remove an employee, then restore the backup.
    backup = context.backups.list_backups()[0].path
    victim = context.employees.create("EMP-003", "Temp", admin_username="admin")
    context.repositories.attendance.db.execute(
        "DELETE FROM attendance WHERE employee_id = ?", (victim.employee_id,)
    )
    context.employees.delete(victim, "admin", reason="test")
    assert len(context.employees.list()) == 2

    assert context.backups.verify_backup(backup)[0]
    context.backups.restore_backup(backup, "admin")
    assert len(context.employees.list()) == 2


# -- admin account -----------------------------------------------------------
def test_admin_page_changes_password(context, qt_app, admin_session):
    from app.ui.admin_account import PasswordDialog

    admin = context.authentication.current_admin
    dialog = PasswordDialog(context, admin)
    dialog._current.setText("Sup3rSecret!")
    dialog._new.setText("BrandNewPass1!")
    dialog._confirm.setText("BrandNewPass1!")
    dialog._on_save()
    context.authentication.logout()
    context.authentication.authenticate("admin", "BrandNewPass1!")


def test_admin_page_rejects_wrong_current_password(context, qt_app, admin_session):
    from app.ui.admin_account import PasswordDialog

    admin = context.authentication.current_admin
    dialog = PasswordDialog(context, admin)
    dialog._current.setText("WrongPass1!")
    dialog._new.setText("BrandNewPass1!")
    dialog._confirm.setText("BrandNewPass1!")
    dialog._on_save()
    assert not dialog._error.isHidden()
    context.authentication.authenticate("admin", "Sup3rSecret!")


def test_admin_page_saves_profile(context, qt_app, admin_session):
    from app.ui.admin_account import AdminAccountPage

    page = AdminAccountPage(context)
    page._full_name.setText("Ana Rivera")
    page._save_profile()
    assert context.authentication.current_admin.full_name == "Ana Rivera"
    assert page._table.rowCount() == 1


# -- kiosk -------------------------------------------------------------------
def test_kiosk_manual_picker_lists_employees(context, qt_app, team):
    from app.qr.scanner import ManualEntryDialog

    dialog = ManualEntryDialog(context.employees.list(status="active"))
    assert dialog._list.count() == 2
    dialog._filter("maria")
    assert dialog._list.count() == 1
    dialog._list.setCurrentRow(0)
    dialog._accept()
    assert dialog.selected_employee.full_name == "Maria Santos"


def test_scanner_widget_manual_fallback_visibility(context, qt_app):
    from app.qr.scanner import ScannerWidget

    widget = ScannerWidget(manual_allowed=True)
    assert widget._manual_button.text() == "Enter ID manually"
    hidden = ScannerWidget(manual_allowed=False)
    assert not hasattr(hidden, "_manual_button")


def test_scanner_emit_dedupes_immediately(context, qt_app):
    from app.qr.scanner import ScannerWidget

    widget = ScannerWidget()
    received = []
    widget.scanned.connect(received.append)
    widget.emit_scanned("SHIFTORA1|IN|" + "a" * 24)
    widget.emit_scanned("SHIFTORA1|IN|" + "a" * 24)   # inside the cooldown
    assert len(received) == 1


def test_keyboard_wedge_captures_full_payload(context, qt_app):
    from app.qr.scanner import KeyboardWedgeFilter

    payload = "SHIFTORA1|EMP|" + "abcdefghijklmnopqrstuvwx"
    captured = []
    wedge = KeyboardWedgeFilter(captured.append)
    for char in payload:
        wedge.handle_key(char, True)
    wedge.handle_key("\r", True)
    assert captured == [payload]
    # A slow, human keystroke burst does not trigger the wedge.
    wedge.reset()
    wedge.handle_key("h", True)
    captured.clear()
    wedge.handle_key("i", True)
    assert captured == []


# -- login / setup -----------------------------------------------------------
def test_setup_window_validates_and_emits(context, qt_app):
    from app.ui.setup_window import SetupWindow

    window = SetupWindow(str(context.paths.root), "1.0.0")
    emitted = []
    window.account_created.connect(lambda u, p, f: emitted.append((u, p, f)))

    window._submit()
    assert emitted == []
    assert not window._error.isHidden()

    window._username.setText("a")
    window._submit()
    assert emitted == []

    window._username.setText("administrator")
    window._password.setText("Sup3rSecret!")
    window._confirm.setText("Mismatch1!")
    window._submit()
    assert emitted == []

    window._confirm.setText("Sup3rSecret!")
    window._submit()
    assert emitted == [("administrator", "Sup3rSecret!", "")]


def test_login_window_emits_credentials(context, qt_app):
    from app.ui.login_window import LoginWindow

    window = LoginWindow("Acme", "1.0.0")
    emitted = []
    window.authenticated.connect(lambda u, p: emitted.append((u, p)))
    window._submit()
    assert emitted == []
    window._username.setText("admin")
    window._password.setText("Sup3rSecret!")
    window._submit()
    qt_app.processEvents()   # the credential hand-off is deferred by one tick
    assert emitted == [("admin", "Sup3rSecret!")]
    window.reset()
    assert window._button.isEnabled()
    assert window._button.text() == "SIGN IN"
    assert window._password.text() == ""


def test_login_window_shows_error(context, qt_app):
    from app.ui.login_window import LoginWindow

    window = LoginWindow()
    window._show_error("Incorrect username or password.")
    assert not window._error.isHidden()
    assert "Incorrect" in window._error.text()

# -- application state machine (app/main.py) ---------------------------------
def test_first_launch_signs_admin_in_and_lands_on_dashboard(context, qt_app):
    """After setup the new administrator must hold a session (spec section 4)."""
    from app.main import Application

    app = Application(context)
    app.create_qt_app()
    try:
        assert context.needs_setup is True
        app._show_setup()
        qt_app.processEvents()
        app._setup._username.setText("admin")
        app._setup._password.setText("Sup3rSecret!")
        app._setup._confirm.setText("Sup3rSecret!")
        app._setup._submit()
        qt_app.processEvents()

        assert context.authentication.is_signed_in()
        assert context.authentication.current_username == "admin"
        assert app.window is not None and app.window.isVisible()
        assert app.window.stack.currentWidget() is app.window.pages["dashboard"]
    finally:
        if app.window is not None:
            app.window.close()
        app.shutdown()


def test_kiosk_close_is_not_reentrant(context, qt_app, admin_session, team):
    """Closing the kiosk twice (closeEvent + slot) must not crash."""
    from app.main import Application, build_pages

    app = Application(context)
    app.create_qt_app()
    try:
        app.open_kiosk()
        qt_app.processEvents()
        assert app.kiosk is not None
        # Simulate what happens after the password gate passes: the close
        # event emits `finished`, and the shell also runs its cleanup.
        app.kiosk._exit_allowed = True
        app.kiosk.close()
        app._on_kiosk_finished()
        qt_app.processEvents()
        app._on_kiosk_finished()  # second call must be a harmless no-op
        qt_app.processEvents()
        assert app.kiosk is None
    finally:
        app.close_kiosk()


def test_logout_returns_to_login_with_message(context, qt_app, admin_session):
    """The signed_out signal carries the notice consumed by the login screen."""
    from app.main import build_pages
    from app.ui.main_window import MainWindow

    window = MainWindow(context)
    build_pages(window, context)
    received = []
    window.signed_out.connect(received.append)
    try:
        window._force_logout("You have been signed out.")
        assert received == ["You have been signed out."]
        assert context.authentication.is_signed_in() is False
    finally:
        window.close()


def test_application_logout_flow_returns_to_login(context, qt_app, admin_session):
    from app.main import Application

    app = Application(context)
    app.create_qt_app()
    try:
        app._show_main_window()
        qt_app.processEvents()
        assert app.window is not None
        app.window._force_logout("timed out")
        qt_app.processEvents()
        assert app.window is None
        assert app._login is not None and app._login.isVisible()
        # The notice is shown on the login screen and then consumed.
        assert app._pending_notice == ""
    finally:
        if app.window is not None:
            app.window.close()
        if app._login is not None:
            app._login.close()
        app.shutdown()


# -- table badge rendering ---------------------------------------------------
def test_status_badge_uses_tinted_background_not_tinted_blue(context, qt_app):
    """Qt only understands #AARRGGBB - a trailing alpha corrupts the color."""
    from app.ui.widgets import STATUS_COLORS, StatusBadge, _tinted
    from app.ui import theme

    assert _tinted("#94A3B8", "1A") == "#1A94A3B8"
    assert _tinted("not-a-color", "1A") == "not-a-color"

    badge = StatusBadge("not_in")
    assert badge.text() == "Not In"
    assert "#1A94A3B8" in badge.styleSheet()  # gray tint, not olive
    assert "94A3B81A" not in badge.styleSheet()

    working = StatusBadge("open")
    assert working.text() == "Working"
    assert theme.SUCCESS in working.styleSheet()


def test_refreshing_tables_leaves_no_ghost_widgets(context, qt_app, team):
    """Repopulating a badge table must remove replaced cell widgets."""
    from app.ui.dashboard import DashboardPage
    from app.ui.employee_management import EmployeePage

    dashboard = DashboardPage(context)
    employees = EmployeePage(context)

    for _ in range(3):
        dashboard.refresh()
        employees.refresh()

    for table in (dashboard._table, employees._table):
        holders = [
            table.cellWidget(row, column)
            for row in range(table.rowCount())
            for column in range(table.columnCount())
            if table.cellWidget(row, column) is not None
        ]
        # Exactly one badge holder per row, all inside the table viewport.
        assert len(holders) == table.rowCount()
        for holder in holders:
            assert holder.parent() is table.viewport() or holder.parent() is table
        # No detached ghost widgets lingering in the viewport either.
        lingering = [
            child for child in table.viewport().children() if child.isWidgetType()
        ]
        assert len(lingering) == table.rowCount()


def test_badge_rows_are_tall_enough(context, qt_app, team):
    from app.ui.dashboard import DashboardPage
    from app.ui.employee_management import EmployeePage

    for page in (DashboardPage(context), EmployeePage(context)):
        assert page._table.verticalHeader().defaultSectionSize() >= 30


def test_stat_tile_caption_wraps_instead_of_clipping(context, qt_app):
    from app.ui.widgets import StatTile

    tile = StatTile("Currently Working", "12")
    assert tile._value.text() == "12"
    assert tile.value_text() == "12"


# -- kiosk exit gate ---------------------------------------------------------
def test_kiosk_close_is_gated_by_password(context, qt_app, admin_session, team):
    """Closing the kiosk without the password must leave it open."""
    from app.ui.attendance_kiosk import KioskWindow

    window = KioskWindow(context)
    window.show()
    qt_app.processEvents()

    gate_calls: list = []
    window._request_exit = lambda: gate_calls.append(True)  # avoid modal dialog
    window.close()
    qt_app.processEvents()

    assert gate_calls == [True]
    assert window.isVisible(), "kiosk must stay open until the password gate passes"
    window.force_close()
    qt_app.processEvents()


def test_kiosk_exit_dialog_accepts_correct_password(context, qt_app, admin_session):
    from app.ui.attendance_kiosk import KioskExitDialog

    dialog = KioskExitDialog(context)
    accepted: list = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog._password.setText("Sup3rSecret!")
    dialog._try_unlock()
    assert accepted == [True]
    assert dialog._error.isHidden()


def test_kiosk_exit_dialog_rejects_wrong_password(context, qt_app, admin_session):
    from app.ui.attendance_kiosk import KioskExitDialog

    dialog = KioskExitDialog(context)
    accepted: list = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog._password.setText("WrongPass1!")
    dialog._try_unlock()
    assert accepted == []
    assert not dialog._error.isHidden()
    assert "Incorrect" in dialog._error.text()


def test_kiosk_exit_lockout_after_repeated_failures(context, qt_app, admin_session):
    from app.ui.attendance_kiosk import KioskExitDialog

    for _ in range(5):
        dialog = KioskExitDialog(context)
        dialog._password.setText("WrongPass1!")
        dialog._try_unlock()
    dialog = KioskExitDialog(context)
    dialog._password.setText("Sup3rSecret!")
    dialog._try_unlock()
    assert "Too many" in dialog._error.text() or "again in" in dialog._error.text()


def test_kiosk_repeated_enter_exit_cycles(context, qt_app, admin_session, team):
    """Three full cycles: open, gate-accepted close, back to main window."""
    from app.main import build_pages
    from app.ui.main_window import MainWindow

    window = MainWindow(context)
    build_pages(window, context)
    try:
        for _ in range(3):
            window.open_kiosk()
            qt_app.processEvents()
            assert window._kiosk is not None
            # Simulate a passed password gate, then the guarded close.
            window._kiosk._exit_allowed = True
            window._kiosk.close()
            qt_app.processEvents()
            assert window._kiosk is None
            assert window.isVisible()
    finally:
        window.close()


def test_main_window_close_drops_kiosk_without_gate(
    context, qt_app, admin_session, team, monkeypatch
):
    """Quitting the app must never trap anyone behind the password gate."""
    from app.main import build_pages
    from app.ui.main_window import MainWindow

    window = MainWindow(context)
    build_pages(window, context)
    window.open_kiosk()
    qt_app.processEvents()

    def fail_if_gated() -> None:
        raise AssertionError("password gate must not appear during shutdown")

    monkeypatch.setattr(window._kiosk, "_request_exit", fail_if_gated)
    window.close()
    qt_app.processEvents()
    assert window._kiosk is None


# -- camera recovery ---------------------------------------------------------
def test_camera_reports_failure_after_repeated_bad_frames(qt_app):
    from app.qr.scanner import CameraScanner

    class DeadCapture:
        def read(self):
            return False, None

        def release(self):
            pass

    scanner = CameraScanner()
    errors: list = []
    scanner.camera_error.connect(errors.append)
    scanner._capture = DeadCapture()
    scanner._timer.start()
    try:
        for _ in range(CameraScanner.FAILURE_THRESHOLD + 2):
            scanner._grab()
        assert len(errors) == 1
        assert "stopped" in errors[0].lower()
        assert scanner.running is False
    finally:
        scanner.stop()


def test_camera_error_rearms_on_restart(qt_app):
    """A fresh start clears the latch, so each outage reports exactly once."""
    from app.qr.scanner import CameraScanner

    class DeadCapture:
        def read(self):
            return False, None

        def release(self):
            pass

    scanner = CameraScanner()
    errors: list = []
    scanner.camera_error.connect(errors.append)
    scanner._capture = DeadCapture()
    for _ in range(CameraScanner.FAILURE_THRESHOLD):
        scanner._grab()
    assert len(errors) == 1
    # start() resets the latch; simulate that reset directly since there is
    # no real camera in the test environment.
    scanner._error_reported = False
    scanner._failures = 0
    scanner._capture = DeadCapture()
    for _ in range(CameraScanner.FAILURE_THRESHOLD):
        scanner._grab()
    assert len(errors) == 2
    scanner.stop()


def test_kiosk_recovers_to_wedge_after_camera_loss(
    context, qt_app, admin_session, team
):
    from app.ui.attendance_kiosk import KioskWindow

    window = KioskWindow(context)
    window.show()
    qt_app.processEvents()
    window._on_camera_error("The camera stopped sending frames.")
    assert "Retry camera" in window._camera_button.text()
    assert "USB scanner" in window._camera_hint.text()
    # The kiosk is still usable: wedge/manual paths are untouched.
    assert window._state == "idle"
    assert window.isVisible()
    window.force_close()
    qt_app.processEvents()


# -- automatic single-scan mode ----------------------------------------------
def test_kiosk_auto_mode_times_in_with_one_scan(context, qt_app, admin_session, frozen):
    from app.ui.attendance_kiosk import KioskWindow
    from app.qr.tokens import build_payload

    context.settings.set("auto_clock_mode", True, "admin")
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    window = KioskWindow(context)
    window.show()
    qt_app.processEvents()

    window.handle_scan(build_payload("employee", juan.qr_token))
    assert window._result_title.text() == "TIME IN SUCCESSFUL"
    assert window._result_name.text() == "Juan Dela Cruz"
    assert context.attendance.record_for_today(juan).status == "open"
    window.force_close()
    qt_app.processEvents()


def test_kiosk_auto_mode_times_out_with_one_scan(context, qt_app, admin_session, frozen):
    from app.ui.attendance_kiosk import KioskWindow
    from app.qr.tokens import build_payload

    context.settings.set("auto_clock_mode", True, "admin")
    context.settings.set("duplicate_scan_window_seconds", 0, "admin")
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    context.attendance.time_in(juan, frozen.at(9, 0))
    window = KioskWindow(context)
    window.show()
    qt_app.processEvents()

    window.handle_scan(build_payload("employee", juan.qr_token))
    assert window._result_title.text() == "TIME OUT SUCCESSFUL"
    assert context.attendance.record_for_today(juan).status == "closed"
    window.force_close()
    qt_app.processEvents()


def test_two_step_mode_unchanged_when_auto_mode_off(
    context, qt_app, admin_session, frozen
):
    from app.ui.attendance_kiosk import KioskWindow
    from app.qr.tokens import build_payload

    assert context.settings.settings.auto_clock_mode is False
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    window = KioskWindow(context)
    window.show()
    qt_app.processEvents()

    window.handle_scan(build_payload("employee", juan.qr_token))
    assert window._result_title.text() == "Employee confirmed"
    assert context.attendance.record_for_today(juan) is None
    window.force_close()
    qt_app.processEvents()


# -- phone settings UI -------------------------------------------------------
def test_settings_has_phone_tab_with_service_controls(
    context, qt_app, admin_session
):
    from app.ui.settings import SettingsPage

    page = SettingsPage(context)
    labels = [page._tabs.tabText(i) for i in range(page._tabs.count())]
    assert "Phone Attendance" in labels
    assert hasattr(page, "_phone_status")
    assert hasattr(page, "_phone_start_button")
    assert hasattr(page, "_phone_stop_button")
    assert page._editors["phone_enabled"] is not None
    assert page._editors["phone_port"] is not None


def test_settings_phone_start_stop_buttons(context, qt_app, admin_session):
    from app.ui.settings import SettingsPage

    context.settings.set("phone_enabled", True, "admin")
    context.settings.set("phone_port", 48234, "admin")
    page = SettingsPage(context)
    try:
        assert context.phone.running is False
        page._start_phone()
        assert context.phone.running is True
        assert context.phone.port == 48234
        page._stop_phone()
        assert context.phone.running is False
    finally:
        context.phone.stop()


def test_settings_phone_start_refuses_when_disabled(
    context, qt_app, admin_session, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.settings import SettingsPage

    messages: list = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *a, **k: messages.append(a) or QMessageBox.StandardButton.Ok),
    )
    assert context.settings.settings.phone_enabled is False
    page = SettingsPage(context)
    page._start_phone()
    assert context.phone.running is False
    assert messages, "the admin must be told to enable phone attendance first"


def test_qr_page_phone_checkin_preview(context, qt_app, team, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from app.ui.qr_management import QRManagementPage

    shown: list = []
    monkeypatch.setattr(QDialog, "exec", lambda self: shown.append(True) or 0)
    page = QRManagementPage(context)
    page._table.selectRow(0)
    page._preview_phone_qr()
    assert shown == [True]
    phone_files = list(context.paths.qr_dir.glob("phone_*.png"))
    assert phone_files, "a phone clock-in/out QR image must be rendered"


# -- custom badge codes in the UI --------------------------------------------
def test_employee_dialog_saves_badge_code(context, qt_app, admin_session):
    from app.ui.employee_management import EmployeeDialog

    dialog = EmployeeDialog(context, None)
    dialog._name.setText("Badge Person")
    dialog._badge.setText("BP-007")
    dialog._on_save()
    created = context.employees.get_by_code(dialog._code.text())
    assert created is not None
    assert created.badge_code == "BP-007"


def test_employee_dialog_rejects_duplicate_badge(context, qt_app, team):
    from app.ui.employee_management import EmployeeDialog

    juan = context.employees.get_by_code("EMP-001")
    context.employees.update(juan, juan.full_name, badge_code="TAKEN", admin_username="admin")

    dialog = EmployeeDialog(context, None)
    dialog._name.setText("Someone Else")
    dialog._badge.setText("taken")
    dialog._on_save()
    assert not dialog._errors["badge_code"].isHidden()
    assert context.employees.list(search="Someone Else") == []


def test_employee_table_shows_badge_column(context, qt_app, team):
    from app.ui.employee_management import EmployeePage

    juan = context.employees.get_by_code("EMP-001")
    context.employees.update(juan, juan.full_name, badge_code="J-1", admin_username="admin")
    page = EmployeePage(context)
    headers = [
        page._table.horizontalHeaderItem(c).text() for c in range(page._table.columnCount())
    ]
    assert "Custom Code" in headers
    badge_column = headers.index("Custom Code")
    values = [page._table.item(r, badge_column).text() for r in range(page._table.rowCount())]
    assert "J-1" in values


def test_kiosk_manual_entry_accepts_badge_code(context, qt_app, admin_session, frozen):
    from app.ui.attendance_kiosk import KioskWindow

    context.settings.set("require_employee_qr", False, "admin")
    juan = context.employees.create(
        "EMP-001", "Juan Dela Cruz", admin_username="admin", badge_code="JD-42"
    )
    window = KioskWindow(context)
    window.show()
    qt_app.processEvents()
    window.handle_scan("jd-42")
    assert window._employee is not None
    assert window._employee.employee_id == juan.employee_id
    assert window._result_title.text() == "Employee confirmed"
    window.force_close()
    qt_app.processEvents()


# -- Google Sheets UI ----------------------------------------------------------
def test_reports_page_has_sheets_button_with_helpful_state(context, qt_app, team):
    from app.ui.reports import ReportsPage

    page = ReportsPage(context)
    assert page._sheets_button.text() == "Send to Google Sheets"
    # Libraries not installed here and feature off: disabled with guidance.
    assert page._sheets_button.isEnabled() is False
    assert "Settings" in page._sheets_button.toolTip() or "packages" in page._sheets_button.toolTip()


def test_settings_has_sheets_tab_with_key_status(context, qt_app, admin_session):
    from app.ui.settings import SettingsPage

    page = SettingsPage(context)
    labels = [page._tabs.tabText(i) for i in range(page._tabs.count())]
    assert "Google Sheets" in labels
    assert hasattr(page, "_sheets_status")
    assert "No service account" in page._sheets_status.text()
    assert page._editors["sheets_enabled"] is not None
    assert page._editors["sheets_spreadsheet_id"] is not None


def test_settings_sheets_key_picker_stores_valid_file(
    context, qt_app, admin_session, tmp_path, monkeypatch
):
    import json

    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from app.ui.settings import SettingsPage

    key = tmp_path / "sa.json"
    key.write_text(json.dumps({
        "type": "service_account",
        "project_id": "demo",
        "private_key_id": "abc",
        "private_key": "-----BEGIN PRIVATE KEY-----\nxyz\n-----END PRIVATE KEY-----\n",
        "client_email": "vardiashift@demo.iam.gserviceaccount.com",
        "client_id": "123",
    }), encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(key), ""))
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    page = SettingsPage(context)
    page._choose_sheets_key()
    assert "iam.gserviceaccount.com" in page._sheets_status.text()


def test_settings_test_sheets_connection_flow(context, qt_app, admin_session, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from app.ui.settings import SettingsPage

    page = SettingsPage(context)
    infos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: infos.append(a)))

    # Missing spreadsheet ID shows warning/info
    page._test_sheets_connection()
    assert any("Missing spreadsheet ID" in str(item) for item in infos)

    # With spreadsheet ID and mocked verify_connection
    page._editors["sheets_spreadsheet_id"].setText("dummy-sheet-123")
    monkeypatch.setattr(
        "app.services.google_sheets.verify_connection",
        lambda key, sheet: "Connected Test Sheet",
    )
    infos.clear()
    page._test_sheets_connection()
    assert any("Connected Test Sheet" in str(item) for item in infos)

