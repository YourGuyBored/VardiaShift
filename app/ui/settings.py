"""Admin settings: general, work hours, attendance rules, backup and restore."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.constants import WEEKLY_GOAL_PRESETS
from app.models.settings import (
    GROUP_ADVANCED,
    GROUP_APPEARANCE,
    GROUP_ATTENDANCE,
    GROUP_GENERAL,
    GROUP_KIOSK,
    GROUP_PHONE,
    GROUP_SECURITY,
    GROUP_SHEETS,
    GROUP_WORK,
    GROUPS,
)
from app.services.backup_service import BackupError
from app.ui import theme
from app.ui.widgets import Card, GhostButton, PrimaryButton, Select, elide_headers
from app.utils.appearance import ACCENTS, ACCENT_NAMES, DEFAULT_ACCENT

BACKUP_COLUMNS = ["File", "Created", "Size"]

#: A form field wider than this reads worse than the short value inside it.
#: The label column is narrow, so the rest of the row would otherwise stretch
#: a two-line text box across the whole window.
FIELD_WIDTH = 440
TAB_BACKUP = "Backup"

#: Tab labels are shorter than the group names: ten full-length tabs do not fit
#: across the window, and Qt answers an overflowing tab bar by eliding every
#: label instead of scrolling. Settings > Advanced and the backup tools still
#: name themselves in full inside the page.
TAB_LABELS = {
    GROUP_KIOSK: "Kiosk",
    GROUP_PHONE: "Phone",
    GROUP_SHEETS: "Sheets",
}


def tab_label(group: str) -> str:
    """The tab caption for a settings group."""
    return TAB_LABELS.get(group, group)


class _AccentSwatch(QWidget):
    """A named accent as a colour block with its name underneath."""

    def __init__(self, name: str, accent: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SPACING_2XS)

        self._chip = QPushButton(self)
        self._chip.setCheckable(True)
        self._chip.setFixedHeight(44)
        self._chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chip.setToolTip(f"{name} - {accent['PRIMARY']}")
        self._chip.setAccessibleName(f"{name} accent, {accent['PRIMARY']}")
        layout.addWidget(self._chip)

        caption = QLabel(name)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setObjectName("CardHint")
        layout.addWidget(caption)
        self._repaint()

    @property
    def name(self) -> str:
        return self._chip.toolTip().split(" - ")[0]

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt naming
        self._chip.setChecked(checked)
        self._repaint()

    def clicked(self):  # noqa: N802 - mirrors QPushButton for the caller
        return self._chip.clicked

    def _repaint(self) -> None:
        selected = self._chip.isChecked()
        border = self._accent["ACCENT_LIGHT"] if selected else theme.BORDER_STRONG
        width = 3 if selected else 1
        self._chip.setStyleSheet(
            f"QPushButton {{"
            f"  background: {self._accent['PRIMARY']};"
            f"  border: {width}px solid {border};"
            f"  border-radius: {theme.RADIUS_SM}px;"
            f"}}"
            f"QPushButton:hover {{ border-color: {self._accent['ACCENT_LIGHT']}; }}"
        )


class SettingsPage(QWidget):
    """Every persisted preference, grouped, validated and audited on save."""

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._editors: dict[str, QWidget] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)
        root.addLayout(self._header())

        self._tabs = QTabWidget()
        self._configure_tab_bar()
        for group in GROUPS:
            self._tabs.addTab(self._scrollable(self._build_group(group)), tab_label(group))
        self._tabs.addTab(self._scrollable(self._build_backup_tab()), TAB_BACKUP)
        root.addWidget(self._tabs, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._save = PrimaryButton("Save changes", self.save)
        actions.addWidget(self._save)
        self._revert = QPushButton("Discard changes")
        self._revert.setCursor(Qt.CursorShape.PointingHandCursor)
        self._revert.clicked.connect(self.refresh)
        actions.addWidget(self._revert)

        self._reset = QPushButton("Restore defaults")
        self._reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset.clicked.connect(self._reset_defaults)
        actions.addWidget(self._reset)
        actions.addStretch(1)
        root.addLayout(actions)

        self.refresh()

    # -- header --------------------------------------------------------------
    def _configure_tab_bar(self) -> None:
        """Keep the tab bar usable on a narrow window.

        Qt elides every tab label when the row overflows rather than scrolling
        it, so the captions are short (see :data:`TAB_LABELS`) and the arrows
        are only the fallback when even those do not fit.
        """
        bar = self._tabs.tabBar()
        bar.setUsesScrollButtons(True)
        bar.setElideMode(Qt.TextElideMode.ElideRight)
        bar.setToolTip("Settings groups - use the arrows to reach the rest")

    def _scrollable(self, page: QWidget) -> QScrollArea:
        """Wrap a tab so a short window scrolls it instead of crushing it.

        A form taller than the tab gets squeezed past its own minimum and Qt
        draws the labels on top of each other. The first-run window solves the
        same problem the same way.
        """
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(page)
        return area

    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("PageSubtitle")
        column.addWidget(title)
        column.addWidget(self._subtitle)
        row.addLayout(column)
        row.addStretch(1)
        return row

    # -- editors -------------------------------------------------------------
    def _editor_for(self, spec):
        settings = self.context.settings.settings
        current = settings.get(spec.key)

        if spec.type == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(current))
            return widget

        # A short list of allowed values (e.g. the 20/25/30/35/40 hour presets)
        # is friendlier as a drop-down than as a spin box.
        preset_choices = spec.choices if len(spec.choices or ()) <= 12 else ()

        if spec.type in ("choice", "weekday") or preset_choices:
            widget = Select()
            widget.setEditable(False)
            choices = preset_choices or spec.choices or ()
            if spec.key == "default_weekly_goal_hours" and not choices:
                for hours in WEEKLY_GOAL_PRESETS:
                    widget.addItem(f"{hours} hours", hours)
            else:
                for choice in choices:
                    label = str(choice)
                    if spec.suffix:
                        label = f"{label} {spec.suffix}"
                    widget.addItem(label, choice)
            index = widget.findData(current)
            if index >= 0:
                widget.setCurrentIndex(index)
            elif widget.count():
                widget.setCurrentIndex(0)
            widget.setMinimumHeight(38)
            return widget

        if spec.type == "int":
            widget = QSpinBox()
            widget.setRange(int(spec.minimum or 0), int(spec.maximum or 100000))
            widget.setValue(int(current or 0))
            widget.setSuffix(f" {spec.suffix}" if spec.suffix else "")
            return widget

        if spec.type == "float":
            widget = QDoubleSpinBox()
            widget.setDecimals(1)
            widget.setRange(float(spec.minimum or 0), float(spec.maximum or 1000))
            widget.setValue(float(current or 0))
            widget.setSuffix(f" {spec.suffix}" if spec.suffix else "")
            return widget

        if spec.type == "time":
            from app.utils.time_utils import TimeUtils

            widget = QTimeEdit()
            widget.setDisplayFormat("HH:mm")
            try:
                parsed = TimeUtils().parse_time_of_day(str(current))
                widget.setTime(parsed)
            except (ValueError, TypeError):
                pass
            return widget

        widget = QLineEdit(str(current or ""))
        widget.setMinimumHeight(38)
        return widget

    def _build_advanced_note(self) -> QWidget:
        note = QLabel(
            "These settings rarely need changing. The defaults suit most "
            "installations."
        )
        note.setWordWrap(True)
        note.setObjectName("CardHint")
        return note

    # -- appearance ----------------------------------------------------------
    def _build_appearance_preview(self) -> QWidget:
        """Named swatches plus a slice of the real interface.

        Picking a colour repaints the running app straight away, so the choice
        is made against the actual screens rather than against a word.
        """
        card = Card(
            "Preview",
            "The accent carries primary actions, the active navigation item and "
            "live attendance state. Text, tables and borders stay ink on white "
            "whatever you pick.",
        )

        swatches = QHBoxLayout()
        swatches.setSpacing(theme.SPACING_S)
        self._swatches: dict[str, _AccentSwatch] = {}
        for name in ACCENT_NAMES:
            swatch = _AccentSwatch(name, ACCENTS[name])
            swatch.setFixedWidth(96)
            swatch.clicked().connect(
                lambda _=False, chosen=name: self._pick_accent(chosen)
            )
            swatches.addWidget(swatch)
            self._swatches[name] = swatch
        swatches.addStretch(1)
        card.add_layout(swatches)

        self._appearance_preview = QWidget(card)
        self._appearance_preview.setObjectName("PreviewStrip")
        preview_layout = QHBoxLayout(self._appearance_preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(theme.SPACING_S)

        self._preview_rail = QLabel("DASHBOARD")
        self._preview_rail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_rail.setFixedWidth(104)
        self._preview_rail.setFixedHeight(76)
        preview_layout.addWidget(self._preview_rail)

        right = QVBoxLayout()
        right.setSpacing(theme.SPACING_XS)

        # A label rather than a real button: a disabled button would be painted
        # with the disabled colours, which is the opposite of a preview.
        self._preview_button = QLabel("Start attendance kiosk")
        self._preview_button.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self._preview_button)

        row = QHBoxLayout()
        row.setSpacing(theme.SPACING_XS)
        self._preview_badge = QLabel("Working")
        row.addWidget(self._preview_badge)
        self._preview_row = QLabel("Selected row")
        row.addWidget(self._preview_row)
        row.addStretch(1)
        right.addLayout(row)

        preview_layout.addLayout(right, 1)
        card.add(self._appearance_preview)

        note = QLabel(
            "Changing the colour here repaints VardiaShift straight away. "
            "Press Save changes to keep it."
        )
        note.setWordWrap(True)
        note.setObjectName("CardHint")
        card.add(note)
        return card

    def _pick_accent(self, name: str) -> None:
        """Selecting a swatch drives the drop-down, so one path does the work."""
        combo = self._editors.get("accent_color")
        if isinstance(combo, QComboBox):
            index = combo.findText(name)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _pending_accent(self) -> dict[str, str]:
        """The accent the editors currently describe, before it is saved."""
        from app.utils.appearance import resolve

        return resolve(
            str(self._value_of("accent_color") or ""),
            str(self._value_of("custom_accent") or ""),
        )

    def _preview_accent(self) -> None:
        """Repaint the app with the pending accent and refresh the sample."""
        if not hasattr(self, "_appearance_preview"):
            return  # the Appearance tab has not been built yet
        accent = self._pending_accent()
        changed = accent != theme.current_accent()
        theme.use_accent(accent)

        chosen = str(self._value_of("accent_color") or DEFAULT_ACCENT)
        custom = str(self._value_of("custom_accent") or "").strip()
        for name, swatch in getattr(self, "_swatches", {}).items():
            swatch.setChecked(name == chosen and not custom)

        self._preview_rail.setStyleSheet(
            f"background: {accent['BG']}; color: {accent['ACCENT_LIGHT']};"
            f"font-size: 10px; font-weight: 700; letter-spacing: 2px;"
        )
        self._preview_button.setStyleSheet(
            f"background: {accent['PRIMARY']}; color: {theme.TEXT_ON_DARK};"
            f"padding: {theme.SPACING_XS}px {theme.SPACING_M}px;"
            f"font-size: 13px; font-weight: 600;"
        )
        self._preview_badge.setStyleSheet(
            f"color: {accent['PRIMARY']}; background: {theme.alpha(accent['PRIMARY'], '1A')};"
            f"border: 1px solid {theme.alpha(accent['PRIMARY'], '55')};"
            f"border-radius: {theme.RADIUS_PILL}px; padding: 2px 9px;"
            f"font-size: 11px; font-weight: 700;"
        )
        self._preview_row.setStyleSheet(
            f"background: {accent['PRIMARY_SOFT']}; color: {theme.TEXT};"
            f"padding: 2px 9px; font-size: 11px; font-weight: 600;"
        )

        app = QApplication.instance()
        # Re-laying the whole stylesheet out is expensive, and a refresh that
        # did not change the colour has nothing to repaint.
        if changed and app is not None:
            theme.apply_theme(app)

    def _watch_accent_editor(self, key: str, editor: QWidget) -> None:
        """Repaint as soon as the accent being edited changes.

        A typed hex that is not valid yet would otherwise blank the app, so the
        custom field only previews once the text actually parses.
        """
        from app.utils.appearance import is_valid_color

        if key == "accent_color":
            editor.currentIndexChanged.connect(self._preview_accent)
        elif key == "custom_accent":
            editor.textChanged.connect(
                lambda text: self._preview_accent()
                if (not text.strip()) or is_valid_color(text)
                else None
            )

    def _build_group(self, group: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        card = Card("", "")
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        for spec in self.context.settings.settings.specs_for_group(group):
            editor = self._editor_for(spec)
            editor.setMaximumWidth(FIELD_WIDTH)
            self._editors[spec.key] = editor
            label = QLabel(spec.label)
            label.setProperty("role", "field")
            if spec.suffix and spec.type in ("int", "float"):
                label.setText(spec.label)
            form.addRow(label, editor)
            if spec.help:
                hint = QLabel(spec.help)
                hint.setObjectName("CardHint")
                hint.setWordWrap(True)
                form.addRow("", hint)
            if group == GROUP_APPEARANCE:
                self._watch_accent_editor(spec.key, editor)

        card.add_layout(form)
        layout.addWidget(card)
        if group == GROUP_APPEARANCE:
            layout.addWidget(self._build_appearance_preview())
        if group == GROUP_PHONE:
            layout.addWidget(self._build_phone_status_card())
        if group == GROUP_SHEETS:
            layout.addWidget(self._build_sheets_status_card())
        if group == GROUP_ADVANCED:
            layout.addWidget(self._build_advanced_note())
        layout.addStretch(1)
        return page

    def _build_phone_status_card(self) -> QWidget:
        """Live server controls: status, address, start/stop, firewall."""
        from app.phone.server import lan_warning

        card = Card("Phone service", "")
        self._phone_status = QLabel("")
        self._phone_status.setWordWrap(True)
        self._phone_status.setObjectName("CardHint")
        card.add(self._phone_status)

        self._phone_url = QLabel("")
        self._phone_url.setWordWrap(True)
        self._phone_url.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._phone_url.setProperty("role", "mono")
        card.add(self._phone_url)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._phone_start_button = PrimaryButton("Start service", self._start_phone)
        row.addWidget(self._phone_start_button)
        self._phone_stop_button = QPushButton("Stop service")
        self._phone_stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._phone_stop_button.clicked.connect(self._stop_phone)
        row.addWidget(self._phone_stop_button)
        row.addStretch(1)
        card.add_layout(row)

        hint = QLabel(
            "Employees join the same Wi-Fi as this computer, scan their "
            "phone check-in QR, and tap once. Internet is not needed, and "
            "the service never leaves your local network."
        )
        hint.setWordWrap(True)
        hint.setObjectName("CardHint")
        card.add(hint)

        self._phone_firewall = QLabel("")
        self._phone_firewall.setWordWrap(True)
        self._phone_firewall.setObjectName("CardHint")
        card.add(self._phone_firewall)

        firewall_row = QHBoxLayout()
        firewall_row.setSpacing(8)
        self._phone_firewall_allow = PrimaryButton(
            "Allow phones through the firewall", self._allow_phone_firewall
        )
        firewall_row.addWidget(self._phone_firewall_allow)
        self._phone_firewall_remove = GhostButton(
            "Remove firewall rule", self._remove_phone_firewall
        )
        firewall_row.addWidget(self._phone_firewall_remove)
        firewall_row.addStretch(1)
        card.add_layout(firewall_row)
        self._describe_firewall()

        warning = lan_warning()
        if warning:
            self._phone_lan_warning = QLabel(warning)
            self._phone_lan_warning.setWordWrap(True)
            self._phone_lan_warning.setProperty("role", "warning")
            card.add(self._phone_lan_warning)
        self._refresh_phone_status()
        if self.context.phone.running:
            # The service may have auto-started with the app; if so, the card
            # should say what the firewall thinks rather than guess.
            self._refresh_firewall()
        return card

    def _refresh_phone_status(self) -> None:
        if not hasattr(self, "_phone_status"):
            return
        server = self.context.phone
        settings = self.context.settings.settings
        if server.running:
            self._phone_status.setText(
                f"Running on port {server.port}. This computer must stay on "
                "while employees check in."
            )
            self._phone_url.setText(f"Check-in base address:\n{server.display_url()}")
        elif not settings.phone_enabled:
            self._phone_status.setText(
                "Phone attendance is disabled. Tick 'Enable phone attendance' "
                "above, save, then start the service."
            )
            self._phone_url.setText("")
        else:
            self._phone_status.setText(
                f"Stopped. It will listen on port {settings.phone_port} once started."
            )
            self._phone_url.setText("")
        self._phone_start_button.setEnabled(not server.running)
        self._phone_stop_button.setEnabled(server.running)

    def _start_phone(self) -> None:
        settings = self.context.settings.settings
        if not settings.phone_enabled:
            QMessageBox.information(
                self,
                "Phone attendance is disabled",
                "Tick 'Enable phone attendance' and save first.",
            )
            return
        ok, message = self.context.phone.start(settings.phone_port)
        if not ok:
            QMessageBox.warning(self, "Could not start", message)
        self._refresh_phone_status()
        if ok:
            # Loopback is never filtered, so a service that starts fine can
            # still be unreadable from a phone. Say which it is.
            self._refresh_firewall()

    def _stop_phone(self) -> None:
        self.context.phone.stop()
        self._refresh_phone_status()

    # -- phone firewall ------------------------------------------------------
    def _describe_firewall(self) -> None:
        """What the button is for, before anything has been probed."""
        self._phone_firewall.setText(
            "A phone on the same Wi-Fi cannot open the check-in page when the "
            "computer's firewall has no exception for it. The button below "
            "adds one for this port, from the local network only."
        )
        self._phone_firewall_remove.hide()

    def _refresh_firewall(self) -> None:
        """Ask the firewall what it thinks, and offer the matching button."""
        from app.phone import firewall

        if not hasattr(self, "_phone_firewall"):
            return
        port = self.context.settings.settings.phone_port
        state = firewall.detect(port)
        self._phone_firewall.setText(state.detail)
        self._phone_firewall_allow.setVisible(
            state.status in (firewall.BLOCKED, firewall.UNKNOWN)
        )
        self._phone_firewall_remove.setVisible(state.status == firewall.ALLOWED)

    def _allow_phone_firewall(self) -> None:
        from app.phone import firewall

        self._run_firewall_change(firewall.allow)

    def _remove_phone_firewall(self) -> None:
        from app.phone import firewall

        self._run_firewall_change(firewall.remove)

    def _run_firewall_change(self, change) -> None:
        """Run one elevated change. The OS prompt can sit open for a while."""
        port = self.context.settings.settings.phone_port
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = change(port)
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_firewall()
        (QMessageBox.information if result.ok else QMessageBox.warning)(
            self, "Firewall", result.message
        )

    def _build_sheets_status_card(self) -> QWidget:
        """Service-account key status and setup shortcut."""
        from app.services.google_sheets import key_status, sheets_available

        card = Card("Google account link", "")
        self._sheets_status = QLabel("")
        self._sheets_status.setWordWrap(True)
        self._sheets_status.setObjectName("CardHint")
        card.add(self._sheets_status)

        row = QHBoxLayout()
        row.setSpacing(8)
        choose = QPushButton("Choose service account file…")
        choose.setCursor(Qt.CursorShape.PointingHandCursor)
        choose.clicked.connect(self._choose_sheets_key)
        row.addWidget(choose)

        test_btn = QPushButton("Test connection")
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.clicked.connect(self._test_sheets_connection)
        row.addWidget(test_btn)
        row.addStretch(1)
        card.add_layout(row)

        hint = QLabel(
            "Needs the optional sheets packages plus a service-account key "
            "from Google Cloud (Sheets API enabled), with the spreadsheet "
            "shared to that account. Full steps are in the README."
        )
        hint.setWordWrap(True)
        hint.setObjectName("CardHint")
        card.add(hint)

        if not sheets_available():
            missing = QLabel(
                "Sheets libraries are not available in this install, so "
                "uploads are unavailable. From-source installs need: "
                "pip install -r requirements.txt"
            )
            missing.setWordWrap(True)
            missing.setProperty("role", "warning")
            card.add(missing)
        self._refresh_sheets_status()
        return card

    def _refresh_sheets_status(self) -> None:
        if not hasattr(self, "_sheets_status"):
            return
        from app.services.google_sheets import key_status

        state, detail = key_status(self.context.paths.root)
        self._sheets_status.setText(detail)
        self._sheets_status.setProperty(
            "role", "success" if state == "ok" else "warning"
        )
        style = self._sheets_status.style()
        if style is not None:
            style.unpolish(self._sheets_status)
            style.polish(self._sheets_status)

    def _choose_sheets_key(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from app.services.google_sheets import (
            GoogleSheetsError,
            store_service_account_file,
        )

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose service-account key file",
            str(Path.home()),
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            stored = store_service_account_file(path, self.context.paths.root)
        except GoogleSheetsError as exc:
            QMessageBox.warning(self, "Key file rejected", exc.message)
            return
        self._refresh_sheets_status()
        QMessageBox.information(
            self,
            "Key file saved",
            f"The service account key was validated and stored.\n\n{stored}",
        )

    def _test_sheets_connection(self) -> None:
        from app.services.google_sheets import (
            GoogleSheetsError,
            sheets_available,
            stored_key_path,
            verify_connection,
        )

        if not sheets_available():
            QMessageBox.information(
                self,
                "Sheets support not installed",
                "Google Sheets libraries are not available in this install.",
            )
            return

        settings = self.context.settings.settings
        key_file = stored_key_path(self.context.paths.root)
        spreadsheet_id = str(
            self._value_of("sheets_spreadsheet_id")
            or settings.sheets_spreadsheet_id
        ).strip()

        if not spreadsheet_id:
            QMessageBox.information(
                self,
                "Missing spreadsheet ID",
                "Enter a Spreadsheet ID above and try again.",
            )
            return

        try:
            title = verify_connection(key_file, spreadsheet_id)
        except GoogleSheetsError as exc:
            QMessageBox.warning(self, "Connection failed", exc.message)
            return

        QMessageBox.information(
            self,
            "Connection successful",
            f"Successfully connected to Google Sheet:\n\n\"{title}\"",
        )

    # -- values --------------------------------------------------------------
    def _value_of(self, key: str):
        spec_key = key
        widget = self._editors.get(spec_key)
        if widget is None:
            return None
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            return widget.value()
        if isinstance(widget, QTimeEdit):
            return widget.time().toString("HH:mm")
        if isinstance(widget, QComboBox):
            return widget.currentData()
        return widget.text()

    # -- backup tab ----------------------------------------------------------
    def _build_backup_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        top = QHBoxLayout()
        top.setSpacing(12)

        create = PrimaryButton("Create backup now", self._create_backup)
        top.addWidget(create)

        restore = QPushButton("Restore from backup")
        restore.setCursor(Qt.CursorShape.PointingHandCursor)
        restore.clicked.connect(self._restore_backup)
        top.addWidget(restore)

        from_file = QPushButton("Restore from file...")
        from_file.setCursor(Qt.CursorShape.PointingHandCursor)
        from_file.clicked.connect(self._restore_from_file)
        top.addWidget(from_file)

        folder = QPushButton("Open backups folder")
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        folder.clicked.connect(self._open_folder)
        top.addWidget(folder)

        top.addStretch(1)
        layout.addLayout(top)

        info = Card("Database", "")
        self._info_label = QLabel("")
        self._info_label.setTextFormat(Qt.TextFormat.PlainText)
        self._info_label.setWordWrap(True)
        self._info_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._info_label.setProperty("role", "mono")
        info.add(self._info_label)
        layout.addWidget(info)

        backups = Card("Backups", "Timestamped copies stored in your data folder.")
        from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

        self._backup_table = QTableWidget(0, len(BACKUP_COLUMNS))
        self._backup_table.setHorizontalHeaderLabels(BACKUP_COLUMNS)
        self._backup_table.verticalHeader().setVisible(False)
        self._backup_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._backup_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._backup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        elide_headers(self._backup_table)
        self._backup_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        backups.add(self._backup_table, 1)
        layout.addWidget(backups, 1)

        danger = QLabel(
            "Restoring replaces all current data. VardiaShift always saves a safety copy "
            "of the current database first, and both actions are written to the audit log."
        )
        danger.setWordWrap(True)
        danger.setStyleSheet(f"color: {theme.WARNING}; font-size: 11px; font-weight: 600;")
        layout.addWidget(danger)
        return page

    def _selected_backup(self) -> Path | None:
        row = self._backup_table.currentRow()
        if row < 0:
            return None
        item = self._backup_table.item(row, 0)
        if item is None:
            return None
        return Path(item.data(Qt.ItemDataRole.UserRole))

    def _create_backup(self) -> None:
        try:
            path = self.context.backups.create_backup(self.context.current_username)
        except BackupError as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))
            return
        self._load_backups()
        QMessageBox.information(
            self, "Backup created", f"A backup was saved as:\n{path.name}\n\n{path.parent}"
        )

    def _restore_backup(self) -> None:
        path = self._selected_backup()
        if path is None:
            QMessageBox.information(self, "No selection", "Select a backup to restore.")
            return
        self._confirm_restore(path)

    def _restore_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a VardiaShift backup", str(self.context.backups.paths.backups_dir),
            "VardiaShift backup (*.db);;All files (*)",
        )
        if path:
            self._confirm_restore(Path(path))

    def _confirm_restore(self, path: Path) -> None:
        ok, detail = self.context.backups.verify_backup(path)
        if not ok:
            QMessageBox.critical(
                self,
                "Cannot restore",
                f"{path.name} is not a usable VardiaShift backup.\n\n{detail}",
            )
            return

        box = QMessageBox(self)
        box.setWindowTitle("Restore database")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"Restore the database from {path.name}?")
        box.setInformativeText(
            "ALL current attendance data will be replaced by the contents of this "
            "backup.\n\nA safety copy of the current database is saved first, so you "
            "can always go back.\n\nYou will be signed out afterwards so you can sign "
            "in again."
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Restore
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Restore:
            return

        try:
            safety = self.context.backups.restore_backup(
                path, self.context.current_username
            )
        except BackupError as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return

        self.context.settings.refresh()
        from app.ui.main_window import MainWindow

        window = self.window()
        if isinstance(window, MainWindow):
            window.signed_out.emit(
                f"Database restored from {path.name}. Please sign in again.\n"
                f"Safety copy: {safety.name}"
            )

    def _open_folder(self) -> None:
        self.context.backups.open_backups_folder()

    def _load_backups(self) -> None:
        from PySide6.QtWidgets import QTableWidgetItem

        entries = self.context.backups.list_backups()
        self._backup_table.setRowCount(len(entries))
        for index, entry in enumerate(entries):
            values = [entry.name, entry.modified_text, entry.size_text]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
                self._backup_table.setItem(index, column, item)
        if entries:
            self._backup_table.selectRow(0)

    def _load_info(self) -> None:
        info = self.context.backups.database_info()
        lines = [f"{label:<14}{value}" for label, value in info.items()]
        self._info_label.setText("\n".join(lines))

    # -- save ----------------------------------------------------------------
    def save(self) -> None:
        values = {key: self._value_of(key) for key in self._editors}
        try:
            changes = self.context.settings.set_many(
                values, self.context.current_username
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Check your settings", str(exc))
            # A refused save must not leave the app wearing a colour that was
            # never stored.
            self._preview_accent()
            return
        if not changes:
            QMessageBox.information(self, "Nothing to save", "No settings were changed.")
            return
        extra_lines: list[str] = []
        if not self.context.settings.settings.phone_enabled:
            if self.context.phone.running:
                self.context.phone.stop()
                extra_lines.append("  • Phone service stopped (feature disabled)")
        lines = [f"  • {label}" for label, _old, _new in changes] + extra_lines
        QMessageBox.information(self, "Settings saved", "Updated:\n" + "\n".join(lines))
        self.refresh()

    def _reset_defaults(self) -> None:
        answer = QMessageBox.question(
            self,
            "Restore defaults",
            "Reset every setting to its default value?\n\n"
            "Employee records and attendance data are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.context.settings.reset_defaults(self.context.current_username)
        self.refresh()
        QMessageBox.information(self, "Defaults restored", "All settings are back to default.")

    # -- data ----------------------------------------------------------------
    def refresh(self) -> None:
        self.context.settings.refresh()
        self._rebuild_tabs()
        # After the rebuild: the preview widgets only exist once the Appearance
        # tab has been built, and styling them first left them uncoloured.
        # The editors now show the saved values, so the app goes back to the
        # saved accent too - discarding or resetting must undo the preview.
        self._preview_accent()

        info = self.context.backups.database_info()
        self._subtitle.setText(
            f"{info['employees']} employees  •  {info['attendance']} attendance records  •  "
            f"Schema v{self.context.schema_version}  •  {info['backups']} backup(s)"
        )
        self._load_info()
        self._load_backups()
        self._refresh_phone_status()
        self._refresh_sheets_status()

    def _rebuild_tabs(self) -> None:
        """Recreate every settings tab from the persisted values."""
        current = self._tabs.currentIndex()
        while self._tabs.count():
            widget = self._tabs.widget(0)
            self._tabs.removeTab(0)
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._editors.clear()
        for group in GROUPS:
            self._tabs.addTab(self._scrollable(self._build_group(group)), tab_label(group))
        self._tabs.addTab(self._scrollable(self._build_backup_tab()), TAB_BACKUP)
        if 0 <= current < self._tabs.count():
            self._tabs.setCurrentIndex(current)


__all__ = ["BACKUP_COLUMNS", "SettingsPage"]