"""Reusable presentation widgets shared by every Shiftora screen."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme

STATUS_COLORS = {
    "open": theme.SUCCESS,
    "closed": theme.PRIMARY,
    "missing": theme.DANGER,
    "not_in": theme.TEXT_SOFT,
}


class Card(QFrame):
    """White rounded container with an optional title."""

    def __init__(self, title: str = "", hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 16)
        self._layout.setSpacing(12)

        if title:
            header = QLabel(title)
            header.setObjectName("CardTitle")
            self._layout.addWidget(header)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("CardHint")
            hint_label.setWordWrap(True)
            self._layout.addWidget(hint_label)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self._layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout) -> object:
        self._layout.addLayout(layout)
        return layout


class StatTile(QFrame):
    """Large number + caption tile used on the dashboard."""

    def __init__(
        self,
        label: str,
        value: str = "0",
        color: str = theme.TEXT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumWidth(150)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        self._value = QLabel(value)
        self._value.setObjectName("StatValue")
        self._value.setStyleSheet(f"color: {color};")

        caption = QLabel(label.upper())
        caption.setObjectName("StatLabel")
        caption.setWordWrap(True)
        caption.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self._value)
        layout.addWidget(caption)

    def set_value(self, value, color: str | None = None) -> None:
        self._value.setText(str(value))
        if color:
            self._value.setStyleSheet(f"color: {color};")

    def value_text(self) -> str:
        return self._value.text()


def _tinted(color: str, alpha_hex: str) -> str:
    """Apply an alpha channel to a ``#RRGGBB`` color.

    Qt stylesheets only understand ``#AARRGGBB`` (alpha FIRST) - appending the
    alpha bytes at the end silently tints the blue channel instead.
    """
    text = color.lstrip("#")
    if len(text) != 6:
        return color
    return f"#{alpha_hex}{text}"


def badge_stylesheet(color: str) -> str:
    return (
        f"color: {color}; background: {_tinted(color, '1A')};"
        f"border: 1px solid {_tinted(color, '55')};"
        f"border-radius: 10px; padding: 2px 9px; font-size: 11px; font-weight: 700;"
    )


def clear_table_widgets(table) -> None:
    """Remove every cell widget before repopulating a table.

    ``setCellWidget`` does NOT delete the widget it replaces, so refreshing a
    table without this leaves ghost widgets painted at stale positions.
    Deletion is immediate (``shiboken6.delete``) rather than ``deleteLater``,
    which only fires once control returns to a running event loop - too late
    for code paths that repopulate and repaint synchronously.
    """
    import shiboken6

    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            widget = table.cellWidget(row, column)
            if widget is None:
                continue
            table.removeCellWidget(row, column)
            widget.hide()
            widget.setParent(None)
            try:
                if shiboken6.isValid(widget):
                    shiboken6.delete(widget)
            except RuntimeError:
                pass  # C++ object already gone


class StatusBadge(QLabel):
    """Small coloured pill describing an attendance status."""

    def __init__(self, status: str = "", text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status(status, text)

    def set_status(self, status: str, text: str = "") -> None:
        color = STATUS_COLORS.get(status, theme.TEXT_MUTED)
        label = text or {
            "open": "Working",
            "closed": "Timed Out",
            "missing": "Missing Time Out",
            "not_in": "Not In",
        }.get(status, status.replace("_", " ").title())
        self.setText(label)
        self.setStyleSheet(badge_stylesheet(color))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class ActiveBadge(QLabel):
    """Active / Inactive pill for employees."""

    def __init__(self, active: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_active(active)

    def set_active(self, active: bool) -> None:
        color = theme.SUCCESS if active else theme.TEXT_MUTED
        label = "Active" if active else "Inactive"
        self.setText(label)
        self.setStyleSheet(badge_stylesheet(color))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class ProgressBarRow(QWidget):
    """Labelled progress bar with a percentage caption."""

    def __init__(
        self,
        label: str = "Progress",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        top = QHBoxLayout()
        self._label = QLabel(label)
        self._label.setObjectName("CardHint")
        self._percent = QLabel("0%")
        self._percent.setObjectName("CardHint")
        top.addWidget(self._label)
        top.addStretch(1)
        top.addWidget(self._percent)
        layout.addLayout(top)

        from PySide6.QtWidgets import QProgressBar

        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)  # allows 0.1% resolution
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(12)
        layout.addWidget(self._bar)

    def set_value(self, percent: float, label: str | None = None) -> None:
        clamped = max(0.0, min(999.0, float(percent)))
        self._bar.setValue(int(round(clamped * 10)))
        self._percent.setText(f"{clamped:.1f}%" if clamped < 100 else f"{clamped:.1f}%")
        if label:
            self._label.setText(label)

    def set_color(self, color: str) -> None:
        self._bar.setStyleSheet(
            f"QProgressBar {{ background: {theme.BORDER}; border: none; border-radius: 6px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 6px; }}"
        )


class Avatar(QLabel):
    """Circular initials badge."""

    def __init__(self, initials: str = "", size: int = 36, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initials = initials
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(initials)
        self.setStyleSheet(
            f"background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK};"
            f"border-radius: {size // 2}px; font-weight: 700; font-size: {max(10, size // 3)}px;"
        )

    def set_initials(self, initials: str) -> None:
        self._initials = initials
        self.setText(initials)


class EmptyState(QWidget):
    """Friendly placeholder for empty tables."""

    def __init__(
        self,
        title: str = "Nothing here yet",
        message: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        icon = QLabel("\U0001F4C4")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 34px;")

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {theme.TEXT};")

        layout.addWidget(icon)
        layout.addWidget(heading)

        if message:
            body = QLabel(message)
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.setWordWrap(True)
            body.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
            layout.addWidget(body)


class PrimaryButton(QPushButton):
    def __init__(self, text: str, on_click: Callable | None = None, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        theme.variant(self, "primary")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)
        if on_click:
            self.clicked.connect(on_click)


class DangerButton(QPushButton):
    def __init__(self, text: str, on_click: Callable | None = None, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        theme.variant(self, "danger")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)
        if on_click:
            self.clicked.connect(on_click)


class SuccessButton(QPushButton):
    def __init__(self, text: str, on_click: Callable | None = None, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        theme.variant(self, "success")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)
        if on_click:
            self.clicked.connect(on_click)


class GhostButton(QPushButton):
    def __init__(self, text: str, on_click: Callable | None = None, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        theme.variant(self, "ghost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if on_click:
            self.clicked.connect(on_click)


class BarChart(QWidget):
    """Tiny dependency-free bar chart for the weekly trend."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._labels: list[str] = []
        self._goal: float = 0.0
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, values: list[float], labels: list[str], goal: float = 0.0) -> None:
        self._values = list(values)
        self._labels = list(labels)
        self._goal = goal
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        baseline = height - 20

        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawLine(0, baseline, width, baseline)

        if not self._values:
            painter.setPen(QColor(theme.TEXT_SOFT))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data yet")
            return

        peak = max(max(self._values), self._goal or 0, 1.0)
        count = len(self._values)
        slot = width / count
        bar_width = min(38.0, slot * 0.55)

        if self._goal:
            goal_y = baseline - (self._goal / peak) * (baseline - 14)
            pen = QPen(QColor(theme.SUCCESS), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(0, int(goal_y), width, int(goal_y))
            painter.setPen(QColor(theme.SUCCESS))
            font = QFont()
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(2, int(goal_y) - 3, "goal")

        for index, value in enumerate(self._values):
            height_value = (value / peak) * (baseline - 18) if peak else 0
            x = slot * index + (slot - bar_width) / 2
            rect = QBrush(QColor(theme.PRIMARY if value else theme.BORDER))
            painter.fillRect(int(x), int(baseline - height_value), int(bar_width), int(height_value), rect)
            painter.setPen(QColor(theme.TEXT_MUTED))
            font = QFont()
            font.setPointSize(8)
            painter.setFont(font)
            if index < len(self._labels):
                painter.drawText(
                    int(x), height - 6, int(bar_width), 14,
                    Qt.AlignmentFlag.AlignCenter, self._labels[index],
                )

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(360, 130)


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit()
        super().mousePressEvent(event)


__all__ = [
    "ActiveBadge",
    "Avatar",
    "BarChart",
    "Card",
    "ClickableLabel",
    "DangerButton",
    "EmptyState",
    "GhostButton",
    "PrimaryButton",
    "ProgressBarRow",
    "STATUS_COLORS",
    "StatTile",
    "StatusBadge",
    "SuccessButton",
]