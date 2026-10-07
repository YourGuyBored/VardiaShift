"""Report templates: reshaping exports and reading files back in."""

from __future__ import annotations

import pytest

from app.services.report_service import ReportResult
from app.services.report_template import (
    FORMAT_HOURS,
    FORMAT_TEXT,
    KIND_DAILY,
    KIND_RANGE,
    ImportRow,
    ReportTemplate,
    TemplateColumn,
    apply_template,
    builtin_templates,
    duration_to_hours,
    hours_to_duration,
    load_templates,
    parse_tabular,
    resolve_template,
    save_templates,
    to_csv_bytes,
    to_sheet_values,
    write_xlsx,
)


@pytest.fixture
def daily_report():
    return ReportResult(
        title="Daily Attendance Report - 2026-10-06",
        subtitle="VardiaShift  •  2026-10-06",
        headers=[
            "Employee ID",
            "Full Name",
            "Department",
            "Time In",
            "Time Out",
            "Hours",
            "Status",
            "Source",
        ],
        rows=[
            ["EMP-001", "Juan Dela Cruz", "IT", "09:00 AM", "05:14 PM", "8h 14m", "Closed", "Desktop"],
            ["EMP-002", "Maria Santos", "HR", "10:02 AM", "-", "3h 00m", "Open", "Phone"],
        ],
        summary=[("Date", "Tuesday, October 6, 2026"), ("Total hours", "11h 14m")],
        totals=["TOTAL", "", "", "", "", "11h 14m", "2 row(s)", ""],
    )


# -- duration conversion -----------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("8h 14m", 8 + 14 / 60),
        ("8h 00m", 8.0),
        ("0h 00m", 0.0),
        ("12h", 12.0),
        ("30m", 0.5),
        ("-", None),
        ("", None),
        ("Working", None),
        (5, 5.0),
    ],
)
def test_duration_to_hours(text, expected):
    result = duration_to_hours(text)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "value,expected",
    [
        (8.0, "8h 00m"),
        (8 + 14 / 60, "8h 14m"),
        (0.5, "0h 30m"),
        ("", ""),
        (None, ""),
        ("nonsense", "nonsense"),
    ],
)
def test_hours_to_duration(value, expected):
    assert hours_to_duration(value) == expected


def test_hours_round_trip():
    for original in ("0h 00m", "7h 45m", "12h 30m"):
        assert hours_to_duration(duration_to_hours(original)) == original


# -- the model ---------------------------------------------------------------
def test_template_column_defaults_heading_to_key():
    column = TemplateColumn(key="Hours")
    assert column.heading == "Hours"
    assert column.number_format == FORMAT_TEXT
    assert column.included is True


def test_template_column_rejects_unknown_format():
    assert TemplateColumn(key="H", number_format="bogus").number_format == FORMAT_TEXT


def test_template_column_clamps_width():
    assert TemplateColumn(key="H", width=999).width == 60
    assert TemplateColumn(key="H", width=-4).width == 0


def test_template_round_trips_through_dict():
    original = ReportTemplate(
        name="Payroll",
        kind=KIND_RANGE,
        columns=[TemplateColumn(key="Hours", heading="Total", number_format=FORMAT_HOURS)],
    )
    restored = ReportTemplate.from_dict(original.to_dict())
    assert restored.name == "Payroll"
    assert restored.kind == KIND_RANGE
    assert restored.columns[0].heading == "Total"
    assert restored.columns[0].number_format == FORMAT_HOURS


def test_template_rejects_unknown_kind():
    assert ReportTemplate(name="x", kind="nonsense").kind == KIND_DAILY


def test_template_drops_columns_without_a_key():
    assert ReportTemplate(name="x", columns=[TemplateColumn(key="")]).columns == []


def test_duplicate_marks_itself_non_builtin():
    original = builtin_templates()[0]
    clone = original.duplicate("My copy")
    assert clone.builtin is False
    assert clone.name == "My copy"
    assert [c.key for c in clone.columns] == [c.key for c in original.columns]


def test_find_is_case_insensitive():
    template = builtin_templates()[0]
    assert template.find("employee id") is not None
    assert template.find("nope") is None


# -- built-ins ---------------------------------------------------------------
def test_builtin_templates_cover_the_report_kinds():
    kinds = {template.kind for template in builtin_templates()}
    assert KIND_DAILY in kinds
    assert KIND_RANGE in kinds
    assert len(builtin_templates()) >= 4


def test_builtin_columns_are_unique():
    for template in builtin_templates():
        keys = [column.key for column in template.active_columns()]
        assert len(keys) == len(set(keys)), f"{template.name} has duplicate columns"


# -- storage -----------------------------------------------------------------
def test_load_templates_returns_builtins_when_none_saved(context):
    templates = load_templates(context.settings)
    assert len(templates) >= 4
    assert all(not template.builtin or template.name for template in templates)


def test_saved_template_survives_a_reload(context, admin):
    custom = builtin_templates()[0].duplicate("Night shift sheet")
    save_templates(context.settings, [custom], "admin")
    names = {template.name for template in load_templates(context.settings)}
    assert "Night shift sheet" in names
    # built-ins are still available alongside it
    assert any(template.builtin for template in load_templates(context.settings))


def test_corrupt_stored_value_does_not_break_loading(context, admin):
    context.settings.set("report_templates", "{not valid json", "admin")
    templates = load_templates(context.settings)
    assert len(templates) >= 4


def test_resolve_falls_back_to_the_report_itself(context, daily_report):
    template, warnings = resolve_template(context.settings, None, KIND_DAILY, daily_report.headers)
    assert [c.heading for c in template.active_columns()] == daily_report.headers
    assert warnings == []


def test_resolve_warns_about_dropped_columns(context, daily_report):
    template, warnings = resolve_template(
        context.settings, "Compact (id and hours only)", KIND_DAILY, daily_report.headers
    )
    assert template.name == "Compact (id and hours only)"
    assert any("Department" in warning for warning in warnings)


def test_resolve_warns_when_the_template_is_for_another_kind(context, daily_report):
    _template, warnings = resolve_template(
        context.settings, "Audit log", KIND_DAILY, daily_report.headers
    )
    assert any("audit" in warning for warning in warnings)


# -- applying a template -----------------------------------------------------
def test_apply_reshapes_columns_and_order(daily_report):
    template = ReportTemplate(
        name="Compact",
        kind=KIND_DAILY,
        columns=[
            TemplateColumn(key="Employee ID"),
            TemplateColumn(key="Full Name"),
            TemplateColumn(key="Hours", number_format=FORMAT_HOURS),
        ],
    )
    shaped = apply_template(daily_report, template)
    assert shaped.headers == ["Employee ID", "Full Name", "Hours"]
    assert len(shaped.rows) == 2
    assert shaped.rows[0][0] == "EMP-001"
    assert shaped.rows[0][2] == pytest.approx(8 + 14 / 60)


def test_apply_renames_headings(daily_report):
    template = ReportTemplate(
        name="Payroll",
        kind=KIND_DAILY,
        columns=[
            TemplateColumn(key="Employee ID", heading="Staff No."),
            TemplateColumn(key="Full Name", heading="Employee Name"),
        ],
    )
    shaped = apply_template(daily_report, template)
    assert shaped.headers == ["Staff No.", "Employee Name"]


def test_apply_honours_the_include_flag(daily_report):
    template = ReportTemplate(
        name="T",
        kind=KIND_DAILY,
        columns=[
            TemplateColumn(key="Employee ID"),
            TemplateColumn(key="Department", included=False),
        ],
    )
    shaped = apply_template(daily_report, template)
    assert shaped.headers == ["Employee ID"]


def test_apply_can_drop_summary_and_totals(daily_report):
    template = ReportTemplate(
        name="T",
        kind=KIND_DAILY,
        columns=[TemplateColumn(key="Employee ID")],
        include_summary=False,
        include_totals=False,
    )
    shaped = apply_template(daily_report, template)
    assert shaped.summary == []
    assert shaped.totals == []


def test_apply_formats_the_totals_cell(daily_report):
    template = ReportTemplate(
        name="T",
        kind=KIND_DAILY,
        columns=[
            TemplateColumn(key="Employee ID"),
            TemplateColumn(key="Hours", number_format=FORMAT_HOURS),
        ],
    )
    shaped = apply_template(daily_report, template)
    assert shaped.totals[1] == "11.23"


def test_apply_leaves_non_duration_text_alone(daily_report):
    template = ReportTemplate(
        name="T",
        kind=KIND_DAILY,
        columns=[TemplateColumn(key="Status", number_format=FORMAT_HOURS)],
    )
    shaped = apply_template(daily_report, template)
    assert shaped.rows[0][0] == "Closed"


def test_apply_produces_a_plain_number_for_a_dash(daily_report):
    """A '-' duration must not become 0.0, which would read as real work."""
    template = ReportTemplate(
        name="T",
        kind=KIND_DAILY,
        columns=[TemplateColumn(key="Time Out", number_format=FORMAT_HOURS)],
    )
    shaped = apply_template(daily_report, template)
    assert shaped.rows[1][0] is None


def test_apply_to_report_result_round_trips(daily_report):
    template = ReportTemplate(
        name="T", kind=KIND_DAILY, columns=[TemplateColumn(key="Employee ID")]
    )
    shaped = apply_template(daily_report, template)
    result = shaped.to_report_result()
    assert result.headers == ["Employee ID"]
    assert len(result.rows) == 2


# -- export writers ----------------------------------------------------------
def test_csv_contains_the_template_headings(daily_report):
    template = ReportTemplate(
        name="T",
        kind=KIND_DAILY,
        columns=[TemplateColumn(key="Employee ID", heading="Staff No.")],
    )
    text = to_csv_bytes(apply_template(daily_report, template)).decode("utf-8-sig")
    assert "Staff No." in text
    assert "Department" not in text


def test_csv_still_neutralises_formulas(daily_report):
    report = ReportResult(
        title="t",
        subtitle="s",
        headers=["Full Name"],
        rows=[["=1+1"]],
    )
    template = ReportTemplate(
        name="T", kind=KIND_DAILY, columns=[TemplateColumn(key="Full Name")]
    )
    text = to_csv_bytes(apply_template(report, template)).decode("utf-8-sig")
    assert "'=1+1" in text


def test_sheet_values_are_all_strings(daily_report):
    template = ReportTemplate(
        name="T",
        kind=KIND_DAILY,
        columns=[
            TemplateColumn(key="Employee ID"),
            TemplateColumn(key="Hours", number_format=FORMAT_HOURS),
        ],
    )
    rows = to_sheet_values(apply_template(daily_report, template))
    flat = [cell for row in rows for cell in row]
    assert all(isinstance(cell, str) for cell in flat)


def test_write_xlsx_uses_template_widths(daily_report, tmp_path):
    template = ReportTemplate(
        name="T",
        kind=KIND_DAILY,
        columns=[
            TemplateColumn(key="Employee ID", width=30),
            TemplateColumn(key="Full Name", width=44),
        ],
    )
    path = write_xlsx(apply_template(daily_report, template), tmp_path / "out.xlsx")
    assert path.is_file()

    from openpyxl import load_workbook

    sheet = load_workbook(path).active
    assert sheet.column_dimensions["A"].width == 30
    assert sheet.column_dimensions["B"].width == 44


# -- import ------------------------------------------------------------------
def test_import_reads_back_what_we_exported(daily_report, tmp_path):
    template = builtin_templates()[0]
    shaped = apply_template(daily_report, template)
    path = tmp_path / "daily.csv"
    path.write_bytes(to_csv_bytes(shaped))

    preview = parse_tabular(path, template)
    assert preview.ok
    assert len(preview.rows) == 2
    assert preview.rows[0].get("Employee ID") == "EMP-001"
    assert preview.rows[0].get("Hours") == "8h 14m"


def test_import_converts_hours_columns(daily_report, tmp_path):
    template = next(
        t for t in builtin_templates() if t.name == "Daily attendance (hours as numbers)"
    )
    shaped = apply_template(daily_report, template)
    path = tmp_path / "daily.csv"
    path.write_bytes(to_csv_bytes(shaped))

    preview = parse_tabular(path, template)
    assert preview.ok
    # Matched by heading ("Hours Worked") even though the report key is "Hours".
    assert preview.rows[0].get("Hours") == pytest.approx(8 + 14 / 60)


def test_import_matches_renamed_headings(daily_report, tmp_path):
    """A file whose headings were renamed in a spreadsheet maps back by heading."""
    template = ReportTemplate(
        name="Renamed",
        kind=KIND_DAILY,
        columns=[
            TemplateColumn(key="Employee ID", heading="Staff No."),
            TemplateColumn(key="Full Name", heading="Employee Name"),
            TemplateColumn(key="Hours"),
        ],
    )
    shaped = apply_template(daily_report, template)
    path = tmp_path / "renamed.csv"
    path.write_bytes(to_csv_bytes(shaped))

    preview = parse_tabular(path, template)
    assert preview.ok
    assert preview.rows[0].get("Employee ID") == "EMP-001"
    assert preview.rows[0].get("Full Name") == "Juan Dela Cruz"


def test_import_from_xlsx(daily_report, tmp_path):
    template = builtin_templates()[0]
    shaped = apply_template(daily_report, template)
    path = write_xlsx(shaped, tmp_path / "daily.xlsx")

    preview = parse_tabular(path, template)
    assert preview.ok
    assert len(preview.rows) == 2
    assert preview.rows[1].get("Full Name") == "Maria Santos"


def test_import_reports_a_missing_header(tmp_path):
    template = builtin_templates()[0]
    path = tmp_path / "junk.csv"
    path.write_text("nothing\nuseful\nhere\n", encoding="utf-8")
    preview = parse_tabular(path, template)
    assert not preview.ok
    assert any("header" in error.lower() for error in preview.errors)


def test_import_reports_an_empty_file(tmp_path):
    template = builtin_templates()[0]
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    preview = parse_tabular(path, template)
    assert not preview.ok


def test_import_reports_header_but_no_rows(tmp_path):
    template = builtin_templates()[0]
    path = tmp_path / "headeronly.csv"
    path.write_text("Employee ID,Full Name,Hours\n", encoding="utf-8")
    preview = parse_tabular(path, template)
    assert not preview.ok
    assert any("no data rows" in error for error in preview.errors)


def test_import_warns_about_unknown_columns(tmp_path):
    template = ReportTemplate(
        name="T", kind=KIND_DAILY, columns=[TemplateColumn(key="Employee ID")]
    )
    path = tmp_path / "extra.csv"
    path.write_text("Employee ID,Mystery\nEMP-001,x\n", encoding="utf-8")
    preview = parse_tabular(path, template)
    assert preview.ok
    assert any("Mystery" in warning for warning in preview.warnings)


def test_import_warns_about_missing_columns(tmp_path):
    template = ReportTemplate(
        name="T",
        kind=KIND_DAILY,
        columns=[TemplateColumn(key="Employee ID"), TemplateColumn(key="Department")],
    )
    path = tmp_path / "partial.csv"
    path.write_text("Employee ID\nEMP-001\n", encoding="utf-8")
    preview = parse_tabular(path, template)
    assert any("Department" in warning for warning in preview.warnings)
    assert preview.rows[0].get("Department") == ""


def test_import_skips_blank_lines(tmp_path):
    template = ReportTemplate(
        name="T", kind=KIND_DAILY, columns=[TemplateColumn(key="Employee ID")]
    )
    path = tmp_path / "blanks.csv"
    path.write_text("Employee ID\nEMP-001\n\n\nEMP-002\n", encoding="utf-8")
    preview = parse_tabular(path, template)
    assert len(preview.rows) == 2


def test_import_reads_bytes_directly(daily_report):
    template = builtin_templates()[0]
    shaped = apply_template(daily_report, template)
    preview = parse_tabular(to_csv_bytes(shaped), template)
    assert preview.ok
    assert len(preview.rows) == 2


def test_import_handles_a_utf8_bom(tmp_path):
    template = ReportTemplate(
        name="T", kind=KIND_DAILY, columns=[TemplateColumn(key="Employee ID")]
    )
    path = tmp_path / "bom.csv"
    path.write_text("Employee ID\nEMP-001\n", encoding="utf-8-sig")
    preview = parse_tabular(path, template)
    assert preview.ok


def test_import_reports_line_numbers(tmp_path):
    template = ReportTemplate(
        name="T", kind=KIND_DAILY, columns=[TemplateColumn(key="Employee ID")]
    )
    path = tmp_path / "lines.csv"
    path.write_text("Employee ID\nEMP-001\nEMP-002\n", encoding="utf-8")
    preview = parse_tabular(path, template)
    assert preview.rows[0].line == 2
    assert preview.rows[1].line == 3


# -- security ----------------------------------------------------------------
def test_imported_text_is_not_treated_as_a_formula(tmp_path):
    """An imported '=cmd' name must stay inert text."""
    template = ReportTemplate(
        name="T", kind=KIND_DAILY, columns=[TemplateColumn(key="Full Name")]
    )
    path = tmp_path / "evil.csv"
    path.write_text("Full Name\n=1+1\n", encoding="utf-8")
    preview = parse_tabular(path, template)
    assert preview.rows[0].get("Full Name") == "=1+1"
    # and it is sanitised on the way back out
    report = ReportResult(title="t", subtitle="s", headers=["Full Name"], rows=[["=1+1"]])
    template2 = ReportTemplate(
        name="T", kind=KIND_DAILY, columns=[TemplateColumn(key="Full Name")]
    )
    assert "'=1+1" in to_csv_bytes(apply_template(report, template2)).decode("utf-8-sig")