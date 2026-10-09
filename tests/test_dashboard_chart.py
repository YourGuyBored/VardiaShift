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
    assert chart.minimumHeight() >= 140
    assert chart.sizeHint().height() == chart.minimumHeight()
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
