# Changelog

All notable changes to Shiftora are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
* 303 automated pytest tests covering services, QR, reports, backup and GUI.
* Windows build script, Linux build script, PyInstaller spec, and GitHub
  Actions workflows for tests and releases.
