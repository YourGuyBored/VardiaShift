"""Reusable presentation widgets shared by every VardiaShift screen."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPolygon
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme

#: Status colour per attendance state. Resolved through :func:`status_color` at
#: paint time rather than frozen here, so a change of accent is picked up.
STATUS_KEYS = ("open", "closed", "missing", "not_in")


def status_color(status: str) -> str:
    """The colour for an attendance status under the current accent."""
    return theme.status_color(status)


def badge_cell(badge: QWidget) -> QWidget:
    """A table-cell host that places one pill consistently.

    A bare cell widget centres whatever it holds, which staggered the pills
    against their column headers, and QTableWidget will happily hand the host
    less height than the pill needs and clip it. Pinning the height here and
    below the table's row height keeps every pill whole.

    No side margins: the view already lays a cell widget inside the item's
    padding box, so the pill lines up under the column's text on its own. An
    inset here padded the pill twice and left it narrower than its own label,
    which shaved characters off both ends.
    """
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(
        badge, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    layout.addStretch(1)
    holder.setFixedHeight(max(badge.sizeHint().height(), badge.minimumHeight()) + 4)
    holder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return holder


def badge_column_width(badge: QWidget) -> int:
    """The column width a pill needs so it is never squeezed.

    The view lays a cell widget inside the item's padding box - the stylesheet
    pads every cell by ``SPACING_XS SPACING_S`` - so the column has to carry
    that padding on both sides of the pill itself. Sizing from a real pill also
    keeps the column still instead of shifting as the data changes.
    """
    return badge.sizeHint().width() + 2 * theme.SPACING_S


class Card(QFrame):
    """White container with an optional title and a hairline under it."""

    def __init__(self, title: str = "", hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(theme.SPACING_M, theme.SPACING_S, theme.SPACING_M, theme.SPACING_S)
        self._layout.setSpacing(theme.SPACING_S)

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
        # No fixed floor. Seven of these share one row, and a 150px floor made
        # that row 1174px wide - wider than the window can ever be - so Qt drew
        # the last tiles straight over their neighbours at the minimum size.
        # The caption wraps and the values are short, so their own content sets
        # a small enough minimum for the row to fit; the side padding is kept
        # tight for the same reason.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.SPACING_S, theme.SPACING_S, theme.SPACING_S, theme.SPACING_S
        )
        layout.setSpacing(theme.SPACING_2XS)

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
    return theme.alpha(color, alpha_hex)


def badge_stylesheet(color: str) -> str:
    """A status pill: tinted fill, hairline edge, label colour."""
    return (
        f"color: {color}; background: {_tinted(color, '1A')};"
        f"border: 1px solid {_tinted(color, '55')};"
        f"border-radius: {theme.RADIUS_PILL}px; padding: 2px 9px;"
        f"font-size: 11px; font-weight: 700;"
    )


def elide_headers(table) -> None:
    """Let a header ellipsize when its column is squeezed.

    Qt draws a header label that does not fit clipped on both sides, so
    "Employee" reads as "nployee" once a table is narrow. An ellipsis keeps
    the label legible instead.
    """
    table.horizontalHeader().setTextElideMode(Qt.TextElideMode.ElideRight)


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

    #: One height for every pill, so a column of them lines up instead of
    #: stepping by a pixel or two with the font's metrics.
    HEIGHT = 22

    def __init__(self, status: str = "", text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(self.HEIGHT)
        self.set_status(status, text)

    def set_status(self, status: str, text: str = "") -> None:
        color = status_color(status)
        label = text or {
            "open": "Working",
            "closed": "Timed Out",
            "missing": "Missing Time Out",
            "not_in": "Not In",
        }.get(status, status.replace("_", " ").title())
        self.setText(label)
        self.setStyleSheet(badge_stylesheet(color))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        # Set after the stylesheet: repolling a freshly styled widget can clear
        # a size constraint applied earlier, and the pill then renders clipped.
        self.setFixedHeight(self.HEIGHT)


class ActiveBadge(QLabel):
    """Active / Inactive pill for employees."""

    def __init__(self, active: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(StatusBadge.HEIGHT)
        self.set_active(active)

    def set_active(self, active: bool) -> None:
        color = theme.SUCCESS if active else theme.TEXT_SOFT
        label = "Active" if active else "Inactive"
        self.setText(label)
        self.setStyleSheet(badge_stylesheet(color))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(StatusBadge.HEIGHT)


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
        layout.setSpacing(theme.SPACING_XS)

        top = QHBoxLayout()
        self._label = QLabel(label)
        self._label.setObjectName("CardHint")
        self._percent = QLabel("0%")
        self._percent.setProperty("role", "mono")
        top.addWidget(self._label)
        top.addStretch(1)
        top.addWidget(self._percent)
        layout.addLayout(top)

        from PySide6.QtWidgets import QProgressBar

        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)  # allows 0.1% resolution
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(10)
        layout.addWidget(self._bar)

    def set_value(self, percent: float, label: str | None = None) -> None:
        clamped = max(0.0, min(100.0, float(percent)))
        self._bar.setValue(int(round(clamped * 10)))
        self._percent.setText(f"{clamped:.1f}%")
        if label:
            self._label.setText(label)

    def set_color(self, color: str) -> None:
        self._bar.setStyleSheet(
            f"QProgressBar {{ background: {theme.SURFACE_SUNK}; border: none; }}"
            f"QProgressBar::chunk {{ background: {color}; }}"
        )


class Avatar(QLabel):
    """Square initials badge - a tag on a record, not an avatar."""

    def __init__(self, initials: str = "", size: int = 36, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initials = initials
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(initials)
        self._repaint()

    def _repaint(self) -> None:
        self.setStyleSheet(
            f"background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK};"
            f"border: 1px solid {theme.alpha(theme.PRIMARY, '33')};"
            f"border-radius: {theme.RADIUS_SM}px;"
            f"font-family: {theme.FONT_UI}; font-weight: 700;"
            f"font-size: {max(10, self._size // 3)}px;"
        )

    def set_initials(self, initials: str) -> None:
        self._initials = initials
        self.setText(initials)
        self._repaint()


class EmptyState(QWidget):
    """Placeholder for a table or list with nothing in it."""

    def __init__(
        self,
        title: str = "Nothing here yet",
        message: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(theme.SPACING_XS)

        # A short rule instead of an icon: the empty state is a sentence, not
        # a picture, and an emoji would read as decoration on an admin screen.
        rule = QFrame()
        rule.setObjectName("SectionRule")
        rule.setFixedWidth(48)
        rule.setFixedHeight(2)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(rule)
        row.addStretch(1)
        layout.addLayout(row)

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {theme.TEXT};"
        )
        layout.addWidget(heading)

        if message:
            body = QLabel(message)
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.setWordWrap(True)
            body.setObjectName("CardHint")
            layout.addWidget(body)

    def body(self) -> QVBoxLayout:
        return self.layout()  # type: ignore[return-value]


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


class Select(QComboBox):
    """A combo box whose arrow this app draws itself.

    Qt's stylesheet engine has no triangle primitive: the usual border trick
    collapses into a filled block, and the built-in Fusion arrow is neither
    themeable nor the right weight for this interface. Painting it here keeps
    one arrow shape on every platform and lets it follow the text tokens.
    """

    ARROW_HALF_WIDTH = 5
    ARROW_HEIGHT = 3
    ARROW_INSET = 13

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            QColor(theme.TEXT_MUTED if self.isEnabled() else theme.TEXT_SOFT)
        )
        centre_x = self.width() - self.ARROW_INSET
        centre_y = self.height() // 2
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(centre_x - self.ARROW_HALF_WIDTH, centre_y - self.ARROW_HEIGHT),
                    QPoint(centre_x + self.ARROW_HALF_WIDTH, centre_y - self.ARROW_HEIGHT),
                    QPoint(centre_x, centre_y + self.ARROW_HEIGHT),
                ]
            )
        )
        painter.end()


class BarChart(QWidget):
    """Weekly hours per day, drawn by hand so the app needs no chart library.

    The widget is laid out in three bands rather than one: the plotting area,
    the goal rule, and a label strip that is guaranteed to end before the
    bottom edge. An earlier version drew each day label into a rectangle that
    ran past the widget, so the text was sliced in half by the window border.
    """

    #: Reserved at the bottom for day names. Nothing else may be drawn here.
    LABEL_BAND = 22
    #: The height the chart takes whenever there is room.
    PREFERRED_HEIGHT = 140
    #: The least it may be squeezed to. At the window's minimum size the card
    #: has less height than it would like, and with nowhere to go the legend
    #: was drawn straight over the day labels.
    MINIMUM_HEIGHT = 116

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._labels: list[str] = []
        self._goal: float = 0.0
        self.setMinimumHeight(self.MINIMUM_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, values: list[float], labels: list[str], goal: float = 0.0) -> None:
        self._values = list(values)
        self._labels = list(labels)
        self._goal = goal
        self.update()

    def _label_font(self) -> QFont:
        font = QFont()
        font.setPointSize(8)
        return font

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()

        plot_bottom = height - self.LABEL_BAND
        plot_top = 16
        plot_height = max(1, plot_bottom - plot_top)
        font = self._label_font()
        painter.setFont(font)

        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawLine(0, plot_bottom, width, plot_bottom)

        if not self._values:
            painter.setPen(QColor(theme.TEXT_MUTED))
            painter.drawText(
                QRect(0, plot_top, width, plot_height),
                Qt.AlignmentFlag.AlignCenter,
                "No hours recorded this week yet",
            )
            return

        peak = max(max(self._values), self._goal or 0, 1.0)
        count = len(self._values)
        slot = width / count
        bar_width = max(6.0, min(38.0, slot * 0.55))

        if self._goal:
            goal_y = int(plot_bottom - (self._goal / peak) * plot_height)
            painter.setPen(QPen(QColor(theme.SUCCESS), 1, Qt.PenStyle.DashLine))
            painter.drawLine(0, goal_y, width, goal_y)
            painter.setPen(QColor(theme.SUCCESS))
            painter.drawText(2, goal_y - 13, "goal", QRect(0, 0, 60, 12),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for index, value in enumerate(self._values):
            bar_height = (value / peak) * plot_height if peak else 0
            x = slot * index + (slot - bar_width) / 2
            color = theme.PRIMARY if value else theme.SURFACE_SUNK
            painter.fillRect(
                QRect(int(x), int(plot_bottom - bar_height), int(bar_width), int(bar_height)),
                QBrush(QColor(color)),
            )
            if index < len(self._labels):
                painter.setPen(QColor(theme.TEXT_MUTED))
                # The strip stops short of the bottom edge so a label is never
                # drawn against the window border.
                painter.drawText(
                    QRect(
                        int(x),
                        plot_bottom + theme.SPACING_2XS,
                        int(bar_width),
                        self.LABEL_BAND - theme.SPACING_XS,
                    ),
                    Qt.AlignmentFlag.AlignCenter,
                    self._labels[index],
                )

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(360, self.PREFERRED_HEIGHT)


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
    "STATUS_KEYS",
    "Select",
    "StatTile",
    "StatusBadge",
    "SuccessButton",
    "badge_cell",
    "badge_column_width",
    "badge_stylesheet",
    "clear_table_widgets",
    "elide_headers",
    "status_color",
]
