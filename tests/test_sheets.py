"""Google Sheets export: row building, validation, and upload flow (offline fakes)."""

from __future__ import annotations

import json

import pytest

from app.services.google_sheets import (
    GoogleSheetsError,
    build_sheet_values,
    key_status,
    push_report,
    sheet_title_for,
    sheets_available,
    store_service_account_file,
    validate_service_account_file,
    verify_connection,
)


def fake_key(tmp_path, **overrides) -> object:
    payload = {
        "type": "service_account",
        "project_id": "demo",
        "private_key_id": "abc",
        "private_key": "-----BEGIN PRIVATE KEY-----\nxyz\n-----END PRIVATE KEY-----\n",
        "client_email": "vardiashift@demo.iam.gserviceaccount.com",
        "client_id": "123",
    }
    payload.update(overrides)
    path = tmp_path / "sa.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class FakeValues:
    def __init__(self, calls: list) -> None:
        self._calls = calls

    def update(self, **kwargs):
        self._calls.append(("update", kwargs))
        return self

    def execute(self):
        return {"updatedCells": 1}


class FakeSpreadsheets:
    def __init__(self, calls: list, fail_tabs: bool = False) -> None:
        self._calls = calls
        self._fail_tabs = fail_tabs

    def get(self, **kwargs):
        self._calls.append(("get", kwargs))
        return self

    def batchUpdate(self, **kwargs):
        self._calls.append(("batchUpdate", kwargs))
        return self

    def values(self):
        if self._fail_tabs:
            raise RuntimeError("no tabs for you")
        return FakeValues(self._calls)

    def execute(self):
        if self._fail_tabs:
            raise RuntimeError("tab exists")
        return {"properties": {"title": "Company Attendance"}}


class FakeService:
    """Stand-in for the discovery client: records calls, touches no network."""

    def __init__(self, calls: list, fail_tabs: bool = False) -> None:
        self._calls = calls
        self._sheets = FakeSpreadsheets(calls, fail_tabs)

    def spreadsheets(self):
        return self._sheets


@pytest.fixture
def report(context, admin, frozen):
    employee = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    context.attendance.time_in(employee, frozen.at(9, 0))
    context.attendance.time_out(employee, frozen.at(17, 0))
    return context.reports.daily_report(frozen.reference.date(), employee.employee_id)


# -- key file handling -------------------------------------------------------
def test_validate_accepts_service_account_key(tmp_path):
    data = validate_service_account_file(fake_key(tmp_path))
    assert data["client_email"].endswith("iam.gserviceaccount.com")


def test_validate_rejects_wrong_type(tmp_path):
    with pytest.raises(GoogleSheetsError) as excinfo:
        validate_service_account_file(fake_key(tmp_path, type="authorized_user"))
    assert "service-account" in excinfo.value.message
    assert "PRIVATE" not in excinfo.value.message  # key material never leaks


def test_validate_rejects_missing_fields(tmp_path):
    path = tmp_path / "thin.json"
    path.write_text(json.dumps({"type": "service_account"}), encoding="utf-8")
    with pytest.raises(GoogleSheetsError) as excinfo:
        validate_service_account_file(path)
    assert "private_key" in excinfo.value.message


def test_validate_rejects_garbage(tmp_path):
    path = tmp_path / "junk.json"
    path.write_text("not json at all", encoding="utf-8")
    with pytest.raises(GoogleSheetsError):
        validate_service_account_file(path)


def test_validate_rejects_missing_file(tmp_path):
    with pytest.raises(GoogleSheetsError) as excinfo:
        validate_service_account_file(tmp_path / "ghost.json")
    assert excinfo.value.code == "missing_file"


def test_store_copies_into_data_dir(context, tmp_path):
    destination = store_service_account_file(fake_key(tmp_path), context.paths.root)
    assert destination.is_file()
    assert destination.parent == context.paths.root
    state, detail = key_status(context.paths.root)
    assert state == "ok"
    assert "iam.gserviceaccount.com" in detail


def test_store_rejects_bad_file(context, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(GoogleSheetsError):
        store_service_account_file(bad, context.paths.root)
    state, _detail = key_status(context.paths.root)
    assert state == "missing"


def test_key_status_missing(context):
    assert key_status(context.paths.root)[0] == "missing"


# -- row building ------------------------------------------------------------
def test_sheet_values_mirror_the_report(report):
    rows = build_sheet_values(report)
    assert rows[0] == [report.title]
    flat = [cell for row in rows for cell in row]
    assert "EMP-001" in flat
    assert "Juan Dela Cruz" in flat
    assert "8h 00m" in flat
    assert all(isinstance(cell, str) for row in rows for cell in row)


def test_sheet_values_neutralise_formulas(context, admin, frozen):
    context.employees.create("EMP-009", "=HYPERLINK(1)", admin_username="admin")
    report = context.reports.daily_report(frozen.reference.date())
    flat = [cell for row in build_sheet_values(report) for cell in row]
    assert "'=HYPERLINK(1)" in flat
    assert "=HYPERLINK(1)" not in flat


def test_sheet_title_is_capped(report):
    assert sheet_title_for(report, "20260101-120000").startswith("Daily Attendance")
    long_title = sheet_title_for(report, "x" * 200)
    assert len(long_title) <= 100


# -- upload flow -------------------------------------------------------------
def test_push_report_creates_tab_and_writes_values(report):
    calls: list = []
    title, count = push_report(
        "unused.json", "spreadsheet-id", report, "20260101-120000",
        service=FakeService(calls),
    )
    kinds = [kind for kind, _kwargs in calls]
    assert kinds == ["batchUpdate", "update"]
    update_kwargs = calls[1][1]
    assert update_kwargs["spreadsheetId"] == "spreadsheet-id"
    assert update_kwargs["range"] == f"'{title}'!A1"
    values = update_kwargs["body"]["values"]
    assert values[0] == [report.title]
    assert count == len(values)
    assert count > 5


def test_push_report_requires_spreadsheet_id(report):
    with pytest.raises(GoogleSheetsError) as excinfo:
        push_report("unused.json", "  ", report, "stamp", service=FakeService([]))
    assert excinfo.value.code == "no_spreadsheet"


def test_push_report_refuses_empty_report(context):
    empty = context.reports.range_report(
        context.clock.today().replace(year=2001),
        context.clock.today().replace(year=2001),
    )
    assert empty.is_empty
    with pytest.raises(GoogleSheetsError) as excinfo:
        push_report("unused.json", "sheet-id", empty, "stamp", service=FakeService([]))
    assert excinfo.value.code == "empty_report"


def test_push_report_wraps_api_errors(report):
    class Exploding:
        def spreadsheets(self):
            raise RuntimeError("boom")

    with pytest.raises(GoogleSheetsError) as excinfo:
        push_report("unused.json", "sheet-id", report, "stamp", service=Exploding())
    assert excinfo.value.code == "api_error"
    assert "boom" in excinfo.value.message


def test_sheets_available_returns_bool():
    assert isinstance(sheets_available(), bool)


def test_verify_connection_success():
    calls = []
    title = verify_connection("unused.json", "sheet-id-123", service=FakeService(calls))
    assert title == "Company Attendance"
    assert any(call[0] == "get" and call[1]["spreadsheetId"] == "sheet-id-123" for call in calls)


def test_verify_connection_requires_spreadsheet_id():
    with pytest.raises(GoogleSheetsError) as excinfo:
        verify_connection("unused.json", "   ", service=FakeService([]))
    assert excinfo.value.code == "no_spreadsheet"


def test_verify_connection_handles_api_failure():
    class BrokenService:
        def spreadsheets(self):
            raise RuntimeError("permission denied")

    with pytest.raises(GoogleSheetsError) as excinfo:
        verify_connection("unused.json", "sheet-id-123", service=BrokenService())
    assert excinfo.value.code == "api_error"
    assert "permission denied" in excinfo.value.message


