"""The weekly bar chart keeps its day labels fully visible."""

from __future__ import annotations

from PySide6.QtGui import QImage

from app.ui.widgets import BarChart

LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

#: TEXT_MUTED (#64748B) with room for antialiased edges.
_MUTED = (70, 130, 85, 145, 105, 170)


def _shown_chart(qt_app, width: int, labels: list[str] | None = None) -> BarChart:
    chart = BarChart()
    chart.resize(width, chart.minimumHeight())
    chart.set_data([9.0] * len(labels or LABELS), labels or LABELS, 0.0)
    chart.show()
    qt_app.processEvents()
    qt_app.processEvents()
    return chart


def _image(chart: BarChart) -> QImage:
    return chart.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)


def _is_text(image: QImage, x: int, y: int) -> bool:
    pixel = image.pixelColor(x, y)
    low_red, high_red, low_green, high_green, low_blue, high_blue = _MUTED
    return (
        low_red <= pixel.red() <= high_red
        and low_green <= pixel.green() <= high_green
        and low_blue <= pixel.blue() <= high_blue
    )


def _text_pixels_in_bottom_strip(image: QImage) -> int:
    return sum(
        1
        for x in range(image.width())
        for y in range(image.height() - 26, image.height())
        if _is_text(image, x, y)
    )


def test_chart_is_tall_enough_for_bars_and_labels(qt_app):
    chart = BarChart()
    # It takes its preferred height whenever there is room.
    assert chart.sizeHint().height() == BarChart.PREFERRED_HEIGHT
    # On the dashboard's smallest window it is squeezed below that, and has to
    # stay tall enough for the label band plus a plot area worth reading.
    assert chart.minimumHeight() == BarChart.MINIMUM_HEIGHT
    assert BarChart.MINIMUM_HEIGHT < BarChart.PREFERRED_HEIGHT
    assert BarChart.MINIMUM_HEIGHT >= BarChart.LABEL_BAND + 64
    chart.deleteLater()


def test_every_day_label_is_drawn(qt_app):
    chart = _shown_chart(qt_app, 400)
    image = _image(chart)
    slot = image.width() / len(LABELS)
    for index in range(len(LABELS)):
        found = sum(
            1
            for x in range(int(slot * index), int(slot * (index + 1)))
            for y in range(image.height() - 26, image.height())
            if _is_text(image, x, y)
        )
        assert found > 0, f"label {LABELS[index]} is missing"
    chart.deleteLater()


def test_labels_are_not_clipped_by_the_bottom_edge(qt_app):
    """The old label rectangle ended past the widget, so only half showed."""
    chart = _shown_chart(qt_app, 400)
    image = _image(chart)
    edge_text = sum(
        1
        for x in range(image.width())
        if _is_text(image, x, image.height() - 1)
        or _is_text(image, x, image.height() - 2)
    )
    assert edge_text == 0, "label text touches the widget edge"
    assert _text_pixels_in_bottom_strip(image) > 0
    chart.deleteLater()


def test_labels_survive_a_narrow_window(qt_app):
    chart = _shown_chart(qt_app, 300)
    image = _image(chart)
    assert _text_pixels_in_bottom_strip(image) > 0
    edge_text = sum(
        1
        for x in range(image.width())
        if _is_text(image, x, image.height() - 1)
        or _is_text(image, x, image.height() - 2)
    )
    assert edge_text == 0
    chart.deleteLater()


def test_empty_chart_does_not_crash(qt_app):
    chart = BarChart()
    chart.resize(400, chart.minimumHeight())
    chart.set_data([], [], 0.0)
    chart.show()
    qt_app.processEvents()
    chart.deleteLater()


def test_dashboard_labels_match_the_current_week(context, qt_app, admin):
    from app.ui.dashboard import DashboardPage

    page = DashboardPage(context)
    clock = context.clock
    window = clock.week_bounds()
    expected = [clock.day_name(day)[:3] for day in clock.date_range(window.start, window.end)]
    assert page._chart._labels == expected
    page.deleteLater()


# -- the switcher ------------------------------------------------------------
def test_the_chart_card_switches_views(context, qt_app, admin, frozen):
    from app.ui.dashboard import DashboardPage

    context.settings.set("default_shift_start", "09:00", "admin")
    employee = context.employees.create("EMP-001", "Juan Dela Cruz", department="IT", admin_username="admin")
    context.attendance.time_in(employee, frozen.at(9, 30))

    page = DashboardPage(context)
    assert page._chart_title.text() == "This week's hours"
    assert "Daily average" in page._chart_legend.text()

    page._chart_view.setCurrentIndex(1)
    assert page._chart_title.text() == "Late arrivals (this week)"
    assert sum(page._chart._values) == 1
    assert "late arrival" in page._chart_legend.text().lower()

    page._chart_view.setCurrentIndex(2)
    assert page._chart_title.text() == "Hours by department (this week)"
    assert page._chart._labels[-1].startswith("IT")
    assert "department(s)" in page._chart_legend.text()
    page.deleteLater()


def test_many_departments_share_one_bar(context, qt_app, admin, frozen):
    from app.ui.dashboard import DashboardPage

    codes = ["Finance", "Marketing", "Operations", "Sales", "Legal", "Design", "QA"]
    for index, code in enumerate(codes, start=1):
        context.employees.create(
            f"EMP-{index:03d}", f"Person {index}", department=code, admin_username="admin"
        )
        emp = context.employees.get_by_code(f"EMP-{index:03d}")
        context.attendance.time_in(emp, frozen.at(9, 0))
        context.attendance.time_out(emp, frozen.at(10, 0))

    page = DashboardPage(context)
    page._chart_view.setCurrentIndex(2)
    # Five named bars plus one shared "Other": a plot cannot read ten thin ones.
    assert len(page._chart._values) == 6
    assert page._chart._labels[-1] == "Other"
    page.deleteLater()


def test_the_department_chart_merges_staff_without_one(context, qt_app, admin, frozen):
    from app.ui.dashboard import DashboardPage

    with_dept = context.employees.create("EMP-001", "Juan Dela Cruz", department="IT", admin_username="admin")
    without = context.employees.create("EMP-002", "Maria Santos", admin_username="admin")
    for emp in (with_dept, without):
        context.attendance.time_in(emp, frozen.at(9, 0))
        context.attendance.time_out(emp, frozen.at(10, 0))

    page = DashboardPage(context)
    page._chart_view.setCurrentIndex(2)
    labels = page._chart._labels
    assert "IT" in labels and labels[-1].startswith("No depa")
    assert len(labels) == 2
    page.deleteLater()
