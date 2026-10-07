# Changelog

All notable changes to VardiaShift are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

* Renamed the application from Shiftora to VardiaShift: window titles, UI
  branding, the data folder, the database and log filenames, the PyInstaller
  output, the Windows installer, the packaged archives, the app icon, and the
  README screenshots.
* The QR payload prefix is unchanged. It is a wire format rather than a
  brand, so QR cards already printed still scan correctly.

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
