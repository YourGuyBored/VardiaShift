"""PDF and print output: the HTML document the Reports page hands to Qt."""

from __future__ import annotations

import pytest

from app.services.report_service import ReportResult, report_to_html


@pytest.fixture(autouse=True)
def no_blocking_dialogs(monkeypatch):
    """Every system dialog answers itself so a stray box cannot hang the run."""
    from PySide6.QtWidgets import QMessageBox

    for method in ("information", "question", "warning"):
        monkeypatch.setattr(
            QMessageBox,
            method,
            staticmethod(lambda *_a, **_k: QMessageBox.StandardButton.Ok),
        )


def _report() -> ReportResult:
    return ReportResult(
        title="Weekly Report",
        subtitle="Org  •  Mon to Fri",
        headers=["Employee", "Hours"],
        rows=[["Juan Dela Cruz", "8h 00m"], ["<script>", "&x"]],
        summary=[("Period", "2026-10-12 to 2026-10-16")],
        totals=["TOTAL", "8h 00m"],
    )


def test_cells_are_escaped():
    out = report_to_html(_report())
    assert "&lt;script&gt;" in out and "<script>" not in out
    assert "&amp;x" in out


def test_title_subtitle_summary_and_totals_are_there():
    out = report_to_html(_report())
    assert "Weekly Report" in out
    assert "Org" in out
    assert "Period" in out and "2026-10-12" in out
    assert "TOTAL" in out


def test_a_report_without_totals_has_no_footer():
    bare = ReportResult("T", "S", ["A"], [["x"]])
    out = report_to_html(bare)
    assert "tfoot" not in out
    assert "<td>x</td>" in out


def test_numbers_reach_the_paper_as_text():
    numbered = ReportResult("T", "S", ["Name", "Hours"], [["Juan", 8.5]])
    out = report_to_html(numbered)
    assert "<td>8.5</td>" in out


def test_the_reports_page_writes_a_real_pdf(context, qt_app, admin, frozen, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from app.ui.reports import ReportsPage

    emp = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    context.attendance.time_in(emp, frozen.at(9, 0))
    context.attendance.time_out(emp, frozen.at(17, 0))

    page = ReportsPage(context)
    target = tmp_path / "payroll.pdf"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(target), "PDF files (*.pdf)")),
    )
    page._export_pdf()
    page.deleteLater()

    assert target.exists()
    # The PDF header is a real, non-empty document.
    assert target.read_bytes()[:5] == b"%PDF-"


def test_the_print_dialog_declines_without_a_crash(context, qt_app, admin, frozen, monkeypatch):
    from PySide6.QtPrintSupport import QPrintDialog
    from PySide6.QtWidgets import QDialog

    from app.ui.reports import ReportsPage

    emp = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    context.attendance.time_in(emp, frozen.at(9, 0))

    monkeypatch.setattr(
        QPrintDialog, "exec", staticmethod(lambda *_a, **_k: QDialog.DialogCode.Rejected)
    )
    page = ReportsPage(context)
    page._print_report()
    page.deleteLater()
