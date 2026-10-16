# Changelog

All notable changes to VardiaShift are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

* The icon integration test compared a Pillow-compressed PNG byte for byte, and
  the launcher test read a POSIX mode bit on Windows, so both failed on the
  Windows runner while passing on Linux. The icon is now compared by layout and
  pixels, and the execute bit is read from the git index off POSIX. Test-only;
  the application is unchanged. Files: `tests/test_desktop_integration.py`.

## [1.3.0] - 2026-10-16

### Added

* A new visual system: one stylesheet built from a token layer, so the accent
  has a single source of truth instead of being duplicated across every screen.
  The look is an "operations desk" - flat surfaces, hard edges, an ink rail, and
  exactly one accent that means *live*. The default accent is a deep marine
  (`#14508C`) rather than a stock brand blue, and the named accents were
  contrast-checked. Files: `app/ui/theme.py`, `app/utils/appearance.py`.
* An **Appearance** tab in Settings: pick one of six named accents or type a
  custom hex colour, with a live preview of the rail, a primary button, a status
  badge and a table row. A bad hex value is refused with a plain message rather
  than an unstyled window. Files: `app/models/settings.py`,
  `app/services/settings_service.py`, `app/ui/settings.py`,
  `tests/test_appearance.py`.
* A **Tardiness & missing hours** report: every day in a range with what was
  late, what fell short, and the hours a supervisor has to patch, plus week,
  month and per-employee summaries. Files: `app/services/report_service.py`,
  `tests/test_tardiness.py`.
* Webcam support that finds the camera instead of hoping it is device 0:
  `list_cameras()` probes the first indices and the kiosk offers a camera
  picker. A named camera is honoured exactly. Files: `app/qr/scanner.py`,
  `app/ui/attendance_kiosk.py`, `tests/test_camera.py`.
* Bulk attendance reads - minutes by employee, minutes by day, daily totals by
  employee, and one day's records keyed by employee - so the dashboard and the
  weekly report query the whole crew in a few queries instead of a few per
  person. Each is checked against the single-employee read it replaces. Files:
  `app/database/repositories.py`, `app/services/attendance_service.py`,
  `tests/test_bulk_reads.py`.
* `scripts/shoot_ui.py`, which renders every screen to a PNG under the offscreen
  Qt platform, so the design can be reviewed without a display.

### Fixed

* **Reports and backups ignored a time-zone change made in Settings.** Both
  services captured the clock once when they were built, so they kept the old
  zone until the app was restarted. The visible symptom was an open session
  measured against the wrong "now" and reported as most of a day. Both now read
  the clock live, as the attendance service already did. Files:
  `app/services/report_service.py`, `app/services/backup_service.py`,
  `tests/test_reports.py`.
* **The phone service could hand out a QR that opened on the PC and nowhere
  else.** When a VPN or Tailscale held the default route, the address picked for
  the check-in link was the tunnel's (Tailscale uses `100.64.0.0/10`), which a
  phone on the Wi-Fi cannot reach. The address is now ranked - a real private
  LAN address wins over a tunnel - and a machine whose only address is a tunnel
  refuses to print the code and shows the reason in Settings instead. No extra
  setup is needed on a normal network. Files: `app/phone/server.py`,
  `app/ui/settings.py`, `tests/test_phone.py`.
* The setup wizard drew each field's placeholder on top of its caption; the
  fields are now a two-by-two grid inside a scroll area. Files:
  `app/ui/setup_window.py`, `tests/test_login_layout.py`.
* The dashboard's chart labels were clipped, and its "Best day" figure was the
  busiest day's *total* hours shown as decimal hours, which reads as one person
  working a 40-hour day. It is now "Busiest day" in the same `40h 40m` form as
  every other duration. Files: `app/ui/dashboard.py`,
  `tests/test_dashboard_chart.py`.
* The kiosk prompt panel showed a literal `{PRIMARY_SOFT}` where a colour should
  have been, and its clock, exit button and footer were hard to read against the
  rail. Files: `app/ui/attendance_kiosk.py`.
* Combo boxes had no drop-down arrow (Qt's stylesheet engine has no triangle
  primitive), the login password field clipped its own border, and the employees
  header overlapped its table. Files: `app/ui/widgets.py`,
  `app/ui/login_window.py`, `app/ui/employee_management.py`.
* Settings tabs elided their labels; the labels are shorter, with a
  `tab_label(group)` helper as the single lookup. Files: `app/ui/settings.py`.
* `TimeUtils.parse` tried `strptime` patterns before `fromisoformat`, which is
  both slower and, since Python 3.11, narrower. It now tries `fromisoformat`
  first and keeps `strptime` as the fallback. Files: `app/utils/time_utils.py`,
  `tests/test_time_parsing.py`.
* The README screenshots were regenerated for the new design.

### Changed

* Duplicated `[1.1.0]` heading removed, and the previous unreleased section
  released as `[1.2.0]`, matching its tag.
* `APP_VERSION`, `pyproject.toml` and the installer default are now `1.3.0`;
  they had stayed at `1.0.0` through two tagged releases.

## [1.2.0] - 2026-10-07

### Added

* Report templates: a reusable, editable column layout applied to every export.
  A template decides which columns appear, in what order, what each is called,
  how wide it is, and whether a duration is written as text (`8h 12m`) or as a
  decimal number (`8.23`) so a spreadsheet can total it. Six layouts ship built
  in, including a payroll sheet and a compact variant, and any of them can be
  duplicated and adjusted. The Reports page has a template dropdown, an editor
  (reorder, rename, width, number format, include or exclude) and a duplicate
  button. Editing or duplicating a template is audit-logged. Files:
  `app/services/report_template.py`, `app/ui/report_dialogs.py`,
  `app/ui/reports.py`, `tests/test_report_template.py`.
* CSV, XLSX and Google Sheets exports all use the selected template, so the three
  exports of one report are identical. Hours columns written as numbers now reach
  Google Sheets with the same two decimals the other two formats write. Files:
  `app/ui/reports.py`, `app/services/google_sheets.py`, `tests/test_sheets.py`.
* Spreadsheet import on the Reports page: pick a CSV or XLSX attendance file, see
  a preview counting new, changed, skipped and error rows with the detail for
  each, then confirm. Nothing is written until the import is confirmed, and a
  file with any error row cannot be confirmed at all. A daily template has no
  Date column, so the day the report covers is used instead and a single-day file
  imports as-is. Times and dates are read in any format VardiaShift can write,
  including 12-hour and weekday-prefixed dates, so a file exported from
  VardiaShift and edited elsewhere imports back unchanged. Attendance is written
  through `add_missing_session`, which records the reason in the audit log.
  Files: `app/services/report_import.py`, `app/ui/reports.py`,
  `app/ui/report_dialogs.py`, `tests/test_report_import.py`.
* Bulk employee import on the Employees page, using the same importer and preview:
  add or update employees from a CSV or XLSX file, see every row's outcome first,
  then confirm. A repeated ID inside one file is skipped, and a custom code that
  belongs to a different employee is an error rather than a silent reassignment.
  A **Sample file** button saves a CSV to fill in. Files:
  `app/services/report_import.py`, `app/ui/employee_management.py`,
  `tests/test_report_import.py`.
* **Load sample data** on the empty dashboard: three demo employees and a week of
  attendance, so an install can be looked at before anything real is entered. The
  button only appears while sample data is present, and **Remove sample data**
  deletes those employees and their attendance in one click. Sample employees are
  marked with a `sample-` ID prefix and a `sample data` reason in the audit log,
  so removal cannot touch a real employee. Files: `app/services/sample_data.py`,
  `app/ui/dashboard.py`, `tests/test_sample_data.py`.
* First-run setup now asks two questions: how people clock in (Quick, one scan,
  or Strict, own QR then the TIME IN/OUT QR) and the organisation type (School,
  Small office, Shop). The type sets the work week, the weekly goal and the shift
  times. Both are plain settings, so they can be changed later without a
  migration. Files: `app/services/presets.py`, `app/ui/setup_window.py`,
  `app/main.py`, `tests/test_sample_data.py`.
* An **Advanced** tab in Settings holding the four settings that rarely need
  changing: grace period, duplicate scan window, audit log retention and phone
  port. Files: `app/models/settings.py`, `app/ui/settings.py`,
  `tests/test_sample_data.py`.

### Fixed

* **The phone service reported success on a port that was already in use,
  on Windows only.** `http.server` sets `allow_reuse_address = True`, which
  requests `SO_REUSEADDR`. On Linux and macOS that is what allows the service
  to stop and start again on the same port without waiting out `TIME_WAIT`. On
  Windows the option means the opposite: it lets a second socket bind to a
  port that is already being listened on, so two instances would both claim
  the same port and split requests between them unpredictably. The server now
  uses a platform-aware subclass: `SO_REUSEADDR` on Linux and macOS, and
  `SO_EXCLUSIVEADDRUSE` on Windows, set before the bind, which is the option
  that actually prevents sharing. A failed start still closes its socket,
  leaves the service not running, and reports "Could not listen on port ...".
  Files: `app/phone/server.py`. Windows fix not verified locally; verify in CI.
* Reading back an exported spreadsheet was not possible for any template using
  decimal hours. A duration is written as a number in those templates, but the
  parser only understood the `8h 12m` form, so every hours column came back
  empty. Durations now parse from both forms.
* The totals row of an export was read back as if it were data, which would
  have created a record for an employee named TOTAL. Total rows are now
  recognised and skipped.
* A column configured as decimal hours that holds text rather than a duration
  (a status, a note) was replaced with a blank cell. It is now left as-is, so a
  misconfigured column cannot silently discard data.
* Saving a value for a setting that has no declared entry was silently
  discarded. Report templates are stored this way, so every custom template was
  lost on save and the built-ins silently took over. Undeclared keys are now
  stored as given, and only declared settings appear in the audit log.
* A spreadsheet cell holding `08:00 AM` was compared as text against a stored
  timestamp, so an imported row never matched the record it was correcting and
  every re-import looked like a change. Times and dates are now normalised before
  comparison. Files: `app/services/report_import.py`.
* Reading a setting that has no declared entry always returned the default,
  even when a value had been stored for it, which hid the save problem above.
  Stored values are now returned.
* Choosing a `.csv` file that had been moved or deleted raised
  `FileNotFoundError` out of the import instead of a message in the dialog.
  Files: `app/services/report_template.py`.
* Renamed the application from Shiftora to VardiaShift: window titles, UI
  branding, the data folder, the database and log filenames, the PyInstaller
  output, the Windows installer, the packaged archives, the app icon, and the
  README screenshots.
* The QR payload prefix is unchanged. It is a wire format rather than a
  brand, so QR cards already printed still scan correctly.
* README: the clone step said `cd vardiashift` and the project structure listed
  a lower-case folder name, both of which failed on a case-sensitive filesystem.
  The test-count badge was removed rather than kept up to date.

### Conflicts

* The phase asked for the rarely used settings under a collapsed **Advanced**
  section. They are a tab of their own instead of a collapsed panel inside each
  page, because the settings page is already built as tabs and a collapsed panel
  per page would have meant four copies of the same editor. Nothing else changed.
* Sample data is stored in the same tables as real data rather than a separate
  sandbox. A separate sandbox would have meant duplicating the schema and would
  not have shown the real UI working. Removal is by `sample-` ID prefix, which
  no real employee can be given, and is one click.

### Not verified on Windows

* Everything in this phase is platform-neutral except the earlier phone port fix
  in `app/phone/server.py`, which remains CI-only.
* Import reads `.csv` as UTF-8 and `.xlsx` through openpyxl. A UTF-8 file with a
  byte-order mark and CRLF line endings, which is what Excel writes on Windows,
  is handled and covered by `tests/test_report_import_encoding.py`. A UTF-16 CSV
  is not. Check an import of a file saved by Excel on Windows.
* Writing the sample CSV uses `Path.write_text`, which writes `\n` on every
  platform. Excel on Windows opens it without complaint.

### Test by hand

1. Reports: pick **Compact (id and hours only)**, export CSV, open it. Only the
   ID and hours columns are present. Pick **Daily attendance (hours as numbers)**
   and export again: hours read `8.20`, not `8h 12m`.
2. Reports → **Import from file**: export a daily CSV, change one time, import it.
   The preview shows the changed row and nothing else. Cancel. Export again: the
   database is unchanged. Import again and confirm: the changed time is now
   stored, and the change appears in the audit log.
3. Reports → **Edit template**: rename a heading, untick a column, move a column,
   save, export. Check the CSV matches. **Duplicate** creates a copy you can
   change without touching the original.
4. Employees → **Import from file** and **Sample file**: save the sample, fill in
   a row, import it. The preview lists each row; a bad name is an error and the
   Import button stays disabled.
5. Dashboard with no employees: **Load sample data**, then **Remove sample data**.
   Three employees appear and then the dashboard is empty again. A real employee
   added in between survives the removal.
6. Delete the data folder and start the app: the setup window asks how people
   clock in and what kind of organisation it is. Creating the account applies the
   presets, visible on the Settings page.
7. Settings → **Advanced** tab: the four rarely used settings are there and
   still save.

## [1.1.0] - 2026-10-07

### Added

* Optional custom code per employee (badge number, short code or nickname) for
  typing at the kiosk when a QR reader is unavailable. Unique when set, any
  length, and printed on the employee's QR card.
* Phone clock-in and clock-out over the local network. Employees join the same
  Wi-Fi as the VardiaShift computer and open their personal page by scanning a QR
  code, then tap Time in or Time out. No app install and no internet needed.
* Single-scan clocking mode, where one employee scan records the arrival or
  departure automatically.
* Phone service controls in Settings, covering status, LAN address, start and
  stop, port, and start-with-the-app.
* A Source column (Desktop, Phone, Admin correction) on the dashboard, the
  attendance Today view, and the detail reports.
* Optional Google Sheets export, which uploads the current report as a new tab
  in a configured spreadsheet using a service account key.
* A Windows installer (Inno Setup) producing `VardiaShift-Setup-Windows-x64.exe`
  with a Start Menu entry, an optional desktop shortcut, and an uninstaller. The
  release workflow builds it on every version tag.
* `setup_windows.bat` for a one-click install from source, which creates the
  virtual environment, installs everything, and adds a desktop shortcut.
* `.gitattributes` to keep line endings correct for `.bat`, `.iss` and `.sh`
  files across Windows and Linux checkouts.
* Window position and size are remembered between sessions, and re-clamped if
  they no longer fit the screen.
* An "Open QR folder" button on the QR Codes page, matching the existing
  "Open exports folder" button on Reports.
* 425 automated pytest tests covering services, QR, reports, backup, phone,
  Sheets, window sizing, and the GUI.

### Fixed

* The main window could not be moved, resized, or minimized on smaller screens.
  It requested a minimum width of 1180 pixels, which is wider than many laptop
  displays and than the usable area on high-DPI screens, leaving the window
  manager nowhere to place the window. Every window now sizes itself against
  the available screen area.
* The attendance kiosk always opened fullscreen, regardless of the setting, so
  it could never be moved or minimized. The setting is now honoured, and F11
  still toggles fullscreen either way.
* Closing the kiosk no longer returns the admin window to a restored size when
  it was maximized.
* A phone QR code generated while the computer had no local network address
  scanned successfully but opened nothing, because it encoded the placeholder
  host name. VardiaShift now reports the problem instead of producing the code.
* The phone check-in page showed a single button whose label depended on current
  status, so a mistap recorded the opposite action. It now offers separate Time
  in and Time out buttons, and each works once per page load.
* The Windows installer was built by the release workflow but never uploaded, so
  it was missing from every published release.
* The Source column did not show "Admin correction" for corrected records,
  because the source was left untouched when an attendance row was edited. A
  corrected record now reports its correction instead of the original Desktop
  or Phone value forever.
* Manual entry in the kiosk failed on custom codes, reporting a scan error.
* Leaving the kiosk requires the administrator password, and the window close
  button is gated the same way. Quitting the application always works without a
  password, so nobody is trapped.
* Concurrent clock attempts for the same employee are serialised, with the
  database uniqueness constraint as backstop.
* Table badge widgets are removed immediately on refresh instead of leaving
  ghosts at stale positions, and use the correct alpha-tinted colors.
* Webcam failures stop the camera after about a second of bad frames and fall
  back to USB or manual scanning with a retry option.
* VardiaShift no longer crashes on start-up on Windows with
  `ZoneInfoNotFoundError: 'No time zone found with key UTC'`. Windows ships no
  IANA time-zone database, so the time-zone package is now a dependency there,
  and the application falls back to a fixed UTC offset instead of raising.
* A flaky test that asserted a random token contains a digit, which fails about
  1.6% of runs. Replaced with deterministic checks.
* Two tests that failed depending on the day of the week now use weekday-proof
  ranges.
* Test teardown no longer hangs on a leftover kiosk window.

### Security

* Exported CSV and XLSX cells are neutralised against spreadsheet formula
  injection, and the same handling is applied to Google Sheets uploads.
* Database schema v5 adds the `phone` attendance source, a non-negative duration
  guard, and an index on scan-event tokens.
* Database schema v6 adds the optional `badge_code` column, unique when set.
  Existing data migrates in place.
* `.gitignore` excludes attendance databases and key files, so real employee
  data cannot be committed by accident.

## [1.0.0] - 2026-10-03

First public release.

### Added

* Standalone desktop application (Python + PySide6 + SQLite, offline-first).
* First-launch setup: automatic database creation and administrator account.
* Secure admin authentication (PBKDF2-SHA256 hashing, lockout, auto sign-out).
* Employee management: add, edit, deactivate/reactivate, search, per-employee
  weekly goals. Employees with attendance history are never hard-deleted.
* Two-step QR attendance: personal employee QR followed by the Time In or
  Time Out QR. Payloads carry only random tokens, never personal data.
* Kiosk screen with webcam, USB keyboard-wedge and manual-ID input methods.
* Attendance rules: duplicate time-in/out rejection, duplicate-scan window,
  missing time-out flagging, optional auto-close, early time-in flagging.
* Exact duration maths, daily/weekly/monthly totals, weekly goal progress,
  overtime reporting (informational only, never punitive).
* Admin corrections with a full audit trail (who, what, old value, new value,
  reason).
* Daily, weekly, monthly, custom-range and per-employee reports with CSV and
  XLSX export.
* Timestamped database backup, verified restore with automatic safety copy.
* Settings persisted in SQLite: organisation, time zone, date/time formats,
  work week, goals, attendance rules, kiosk behaviour, security.
* Audit log viewer with search, action filter and CSV export.
* 295 automated pytest tests covering services, QR, reports, backup and GUI.
* Windows build script, Linux build script, PyInstaller spec, and GitHub
  Actions workflows for tests and releases.
BUILD STATUS: PHASE 1 DONE 2026-10-07 16:48
