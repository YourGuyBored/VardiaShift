# Changelog

All notable changes to Shiftora are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

* Optional custom code per employee (`badge_code`): free-text badge numbers,
  short codes or nicknames of any length (control characters rejected),
  unique when set. Shown in the
  employee table and on QR cards, searchable, and accepted by manual clock-in
  (kiosk typed entry and the manual picker). Files: `app/models/employee.py`,
  `app/utils/validation.py`, `app/database/migrations.py` (v6),
  `app/database/repositories.py`, `app/services/employee_service.py`,
  `app/ui/employee_management.py`, `app/ui/attendance_kiosk.py`,
  `app/qr/scanner.py`, `app/services/qr_service.py`,
  `tests/test_employees.py`, `tests/test_ui.py`. Why: admins need a
  human-typable identifier without the strict Employee-ID format; the secure
  QR token itself is unchanged. Test with:
  `python -m pytest tests/test_employees.py tests/test_ui.py -k "badge or manual_entry"`.

* Phone clock-in / clock-out over the local network: optional stdlib HTTP
  service with a per-employee page carrying explicit **Time in** and
  **Time out** buttons, single-use tap codes, and a phone QR on the QR Codes
  page ("Phone clock-in / out QR"). Records flow through the existing
  attendance logic and show as "Phone" on the dashboard, in views and in
  reports.
* Single-scan clocking mode (Settings → Attendance): one employee scan
  records time-in or time-out automatically.
* Phone service controls in Settings → Phone Attendance: status, LAN
  address, start/stop, port, auto-start.
* "Source" column (Desktop / Phone / Admin correction) on the dashboard,
  the attendance Today view and the detail reports.
* Optional Google Sheets export: the Reports page can upload the current
  report as a new tab to a configured spreadsheet via a service account.
  Files: `app/services/google_sheets.py`, `app/models/settings.py` (Google
  Sheets group), `app/ui/settings.py` (key-file picker + status),
  `app/ui/reports.py` (Send button), `requirements.txt`,
  `pyproject.toml`, `tests/test_sheets.py`, `tests/test_ui.py`. Why: keep
  attendance data next to anything else stored in Google Sheets. The client
  libraries ship with the app (including the packaged build) so there is
  nothing extra to install; without a key file or internet the button
  explains what is missing and everything else works offline. Test with:
  `python -m pytest tests/test_sheets.py` (uses offline fakes, no network).
  Note: this overrules the older "avoid new dependencies" guidance — the
  feature was explicitly requested and the libraries ride along in the
  existing bundle.
* Windows installer: Inno Setup script (`installer/windows/Shiftora.iss`)
  producing `Shiftora-Setup-Windows-x64.exe` with Start Menu entry, optional
  desktop shortcut and uninstaller; the release workflow now builds it on
  every version tag. `setup_windows.bat` gives from-source users a
  double-click install (venv + dependencies including the Windows time-zone
  database + desktop shortcut). `.gitattributes` pins CRLF for `.bat`/`.iss`
  and LF for `.sh` so checkouts work on both systems. Test the workflow file
  with `python3 -c "import yaml; yaml.safe_load(open(...))"`; the installer
  itself compiles on a Windows machine with Inno Setup 6 (`iscc
  installer/windows/Shiftora.iss`).

### Fixed

* Leaving the kiosk now requires the administrator password; the window
  close button is gated the same way. Quitting the application bypasses the
  gate so nobody gets trapped.
* Table badge widgets are removed immediately on refresh (no more ghosts at
  stale positions) and use correct alpha-tinted colors.
* Concurrent clock attempts for the same employee are serialised, with the
  database uniqueness constraint as backstop.
* Webcam failures stop the camera after ~1 second of bad frames and fall
  back to USB/manual scanning with a retry option.
* Windows crash on login (`ZoneInfoNotFoundError: 'No time zone found with
  key UTC'`). Cause: Windows ships no IANA time-zone database and the
  install lacked the `tzdata` package, so even UTC failed to resolve the
  first time the dashboard asked for the time. Fixed two ways: `tzdata` is
  now a Windows dependency (`requirements.txt`, `pyproject.toml`), and
  `app/utils/time_utils.py` falls back to fixed UTC instead of raising when
  no database exists. Files: `app/utils/time_utils.py`, `requirements.txt`,
  `pyproject.toml`, `tests/test_settings.py`. Test with:
  `python -m pytest tests/test_settings.py -k "tz_database or named_zones"`.
* Test-session teardown hung on a leftover kiosk window: closing it hit the
  password gate's modal dialog after the dialog patch was reverted.
  `tests/conftest.py` now uses `force_close()` for windows that support it
  (the same path as application shutdown).
* Kiosk manual entry crashed on badge codes (`AttributeError`, swallowed as
  "Scan error"): `EmployeeService` had no `get_by_badge_code` passthrough.
  Added it (`app/services/employee_service.py`). The employee dialog now maps
  save errors by error code instead of message text, so the duplicate-badge
  message highlights the right field
  (`app/ui/employee_management.py`). Test with the badge UI tests above.
* Two weekday-fragile tests hardened: the migration test now asserts the
  current `SCHEMA_VERSION` instead of a hardcoded number
  (`tests/test_database.py`), and the attendance history test uses the
  last-week range so it passes on any weekday
  (`tests/test_ui.py`). Test with:
  `python -m pytest tests/test_database.py tests/test_ui.py -k "migration or today_and_history"`.

### Conflicts with your prompt

* Custom codes have no length cap, as asked — but control characters are
  still rejected. Reason: a code containing newlines or control bytes would
  corrupt single-line displays, printed QR-card footers, audit-log lines,
  and CSV structure. Everything else (letters, numbers, spaces, symbols,
  any script, any length SQLite can store) is accepted.

### Review coverage (audit pass)

Every other touched file, with what changed and why:

* `.github/workflows/release.yml` — Windows job now installs Inno Setup
  and compiles the installer, stamping the version from the git tag. Why:
  published releases gain a real `Shiftora-Setup-Windows-x64.exe`.
* `README.md` — rewritten download section (installer first, portable zip,
  source fallback), custom-code docs, Google Sheets setup guide, and the
  one-click commit task. Why: docs must describe what actually ships.
* `app/context.py` — owns the `PhoneServer`, stops it on shutdown, and
  starts it when the auto-start setting says so. Why: single lifecycle
  owner, no orphan threads.
* `app/main.py` — launches phone auto-start after the Qt app exists. Why:
  the service needs settings loaded, which only happens here.
* `app/models/attendance.py` — `AttendanceRecord.source` and
  `EmployeeToday.source` fields. Why: carry the origin through to the UI
  without extra queries.
* `app/phone/__init__.py` — package re-exports for the LAN service. Why:
  stable import surface for UI, tests, and future callers.
* `app/phone/server.py` — the threaded check-in server itself: routes,
  single-use tap codes, per-address throttling, generic 404s. Why: the
  phone attendance feature.
* `app/services/attendance_service.py` — `record_scan` takes a source,
  per-employee locks plus unique-violation recovery against concurrent
  taps, `record_auto_scan`/`resolve_auto_kind` for single-scan mode, and
  `source_label` for display. Why: one shared rulebook for kiosk, phone,
  and corrections.
* `app/services/report_service.py` — Source columns on detail reports and
  the shared `sanitize_spreadsheet_cell` used by CSV, XLSX, and Sheets
  uploads. Why: provenance everywhere, injection nowhere.
* `app/ui/attendance_view.py` — Source column on the Today tab. Why:
  admins see at a glance how each record was created.
* `app/ui/dashboard.py` — Source column on the status table. Why: same,
  on the landing screen.
* `app/ui/main_window.py` — kiosk teardown uses the shutdown path
  (`force_close`), the phone server stops with the window, and the
  sign-out signal carries its message. Why: no trapped admins, no orphan
  server, working logout notice.
* `app/ui/qr_management.py` — "Phone check-in QR" preview per employee.
  Why: the handout that connects a phone to a personal check-in page.
* `tests/test_attendance.py` — auto-scan, source labelling, and source
  rejection cases. Why: pin the new service behaviour.
* `tests/test_phone.py` — new file: server lifecycle, full tap flow,
  revoked/unknown tokens, nonce replay, throttling, 8-thread concurrency.
  Why: the network surface needs adversarial tests.
* `tests/test_reports.py` — Source-column assertions and formula-injection
  cases. Why: exports changed shape and gained a security rule.
* `tests/test_workflow.py` — kiosk windows now close via `force_close`.
  Why: plain `close()` correctly hits the password gate, which would hang
  tests.
* `tests/test_ui.py` — kiosk gate, exit cycles, camera recovery, auto
  mode, badge UI, Sheets UI. Why: every new screen and guard tested.
* `scripts/one_click_commit.py` — new file: test → stage → ask → commit,
  never pushes. Why: the one-click VS Code task needs a shell-neutral
  runner.
* `.vscode/tasks.json` — new file: the one-click commit task. Why: makes
  the flow a single menu item on both systems.
* `.vscode/settings.json` — dropped the hardcoded Linux interpreter path.
  Why: the Python extension auto-discovers `.venv` per OS; the old value
  broke Windows.
* `requirements-optional.txt` — Google libraries removed again (they ship
  in `requirements.txt`). Why: one source of truth, no conflicting advice.

### Security

* Exported CSV/XLSX cells are neutralised against spreadsheet formula
  injection.
* Database schema v5: `phone` attendance source, non-negative duration
  guard, index on scan-event tokens. Existing data migrates in place.

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
* 469 automated pytest tests covering services, QR, reports, backup, phone, sheets, window sizing, commit helpers and GUI.
* Windows build script, Linux build script, PyInstaller spec, and GitHub
  Actions workflows for tests and releases.

## Review

Independent review pass over the whole unreleased batch. Working tree was left
otherwise untouched (`git status` identical before and after apart from the
files listed here).

### Fixed

* **The Windows installer never reached a release.** `release.yml` built
  `Shiftora-Setup-Windows-x64.exe` but the only `upload-artifact` step listed
  `dist/${{ matrix.archive }}`, so the installer was discarded at job end and
  the `publish` job never saw it. The README told Windows users to download
  that exact file from Releases. Added a Windows-only upload step for it
  (`.github/workflows/release.yml`).
* **`.vscode/tasks.json` was uncommittable.** `.gitignore` ignores `.vscode/*`
  and excepted only `extensions.json` and `settings.json`, so the new one-click
  commit task could never be committed despite being documented as a new file.
  Added `!.vscode/tasks.json` (`.gitignore`).
* **Admin corrections did not set the attendance source.** The new Source
  column claims to show "Admin correction", but `update_session` left
  `source` untouched, so a corrected phone or desktop record kept reading
  "Phone"/"Desktop" forever. `update_session` now writes
  `source = 'correction'`, matching `create_record_for_date`, which already
  did. Verified against a real correction: source went `qr` → `correction`,
  label `Desktop` → `Admin correction`, with all 395 tests still passing.

### Corrected documentation

* Custom codes have no length cap (only control characters are rejected), but
  the Unreleased entry and README both still said "up to 64 characters".
  Reworded in both places.
* Test count was 393 in the changelog and README; the suite collects 395.
  Corrected in both.

### Verified, no change needed

* `validate_badge_code` has no length limit and rejects only control
  characters, as asked.
* The `UNCHANGED` sentinel is threaded correctly through both
  `EmployeeRepository.update` and `EmployeeService.update`, including the audit
  `new_value` comparison, so callers that omit `badge_code` leave the stored
  value alone and callers passing `None` clear it.
* `resolve_zone` has a single fallback path to `timezone.utc`.
* `test_payload_has_no_personal_data` is now deterministic: it asserts exact
  payload composition instead of substring-matching short fields like a
  department named "IT" that could appear by chance inside a random token.
* Google libraries are in `requirements.txt` and `pyproject.toml`, removed from
  `requirements-optional.txt`, and the Linux PyInstaller build bundles them
  (`google.auth`, `google.oauth2.service_account`, `googleapiclient.discovery`
  all present in `PYZ-00.toc`).
* `scripts/one_click_commit.py`, exercised in a throwaway `git init` repo, not
  this one: runs pytest first, refuses to stage or commit on failure, never
  pushes (no remote configured and no push call in the file), stages only after
  tests pass, aborts cleanly on an empty commit message, and exits 1 outside a
  git repository. Standard library only, `sys.executable` for pytest, so it is
  shell-neutral.
* No secrets: the only private-key-shaped strings in the tree are fake values
  in `tests/test_sheets.py` and `tests/test_ui.py`. The service-account key is
  copied into the user data directory, never logged, and error messages return
  field names rather than key material.
* No leftover debug code, `print`, `breakpoint`, or `TODO`/`FIXME` in any
  changed file.
* `app/phone/server.py` binds `0.0.0.0` as intended. Its parsing looks sound:
  paths are matched exactly, tokens are compared with `hmac.compare_digest`,
  nonces are single-use and TTL-expiring, unknown tokens return an identical
  generic 404, failures are throttled per address, and all interpolated values
  pass through `html.escape`.

* `test_payload_has_no_personal_data` was still flaky despite the earlier
  determinism work: it asserted the random token "contains a digit", which
  fails about 1.6% of runs (measured over 200k tokens) because a random
  24-character URL-safe token can legitimately have no digits. Caught by
  running the full suite rather than the single test. Replaced with
  deterministic checks (fixed length, URL-safe alphabet)
  (`tests/test_qr.py`).

### Added (phone QR auto-open)

* **The phone QR already opened the browser; confirmed and pinned by a test.**
  It encodes a full `http://<lan-ip>:<port>/c/<token>` URL rather than a
  Shiftora token, which is why pointing a phone camera at it goes straight to
  the page. `test_phone_qr_encodes_a_full_http_url` now asserts the scheme,
  host, port and path so this cannot silently regress into encoding a bare
  token or path-only string (`tests/test_phone.py`). The preview copy now says
  the page "opens by itself" (`app/ui/qr_management.py`).

* **"Open QR folder" button on the QR Codes page**, revealing the folder that
  holds the rendered QR images, matching the existing "Open exports folder"
  button on Reports. Files: `app/services/backup_service.py`
  (`open_qr_folder()`), `app/ui/qr_management.py`,
  `tests/test_database.py`.

### Fixed (windows could not be moved, resized or minimized)

* **The main window could not be moved, resized or minimized on smaller
  screens.** `MainWindow` called `setMinimumSize(1180, 720)`. When the
  available screen area is narrower than that - a small laptop, a HiDPI
  panel, or Windows display scaling at 125%/150% - the window's minimum
  exceeds the screen, and the window manager has nowhere to put it: it
  cannot be dragged, resized or minimized. Confirmed by measurement, not
  guesswork: on an 800px-wide screen the old minimum reported
  "CANNOT FIT: WM cannot move/minimize it". Every top-level window now sizes
  itself against `QScreen.availableGeometry()` (which excludes the taskbar
  and docks) via the new `app/ui/window_sizing.py`, clamped to 90% of the
  screen so there is always room to drag. On that same 800px screen the main
  window's minimum drops from 1180 to 720 and the kiosk from 820 to 720, and
  both now fit.
* **The kiosk always opened fullscreen, whatever the setting said.**
  `show_kiosk()` called `showFullScreen()` unconditionally and only consulted
  `kiosk_fullscreen` to set an internal flag, so the setting had no visible
  effect and the window could never be moved or minimized. Windowed mode is
  now honoured, and F11 still toggles either way. The password gate on
  leaving the kiosk is unchanged.
* **Window position and size are remembered between sessions**, via
  `QSettings` + `saveGeometry`/`restoreGeometry`. Qt re-clamps a stored
  geometry that no longer fits, so a window saved on a large monitor does not
  open off-screen on a small one. A maximized window reopens maximized only
  if it was already up when the app last closed.
* **Closing the kiosk no longer un-maximizes the admin window.** Leaving the
  kiosk restored a saved geometry unconditionally, which could drop a
  maximized admin window back to a small size. The pre-kiosk state is now
  remembered and restored.
* Smaller windows are handled the same way: sign-in, first-time setup, and
  the add/edit-employee and correct-attendance dialogs all clamp to the
  screen.

### Added (committing and publishing)

* **VS Code one-click commit, now safe by default.** `tasks.json` gains four
  tasks: the commit flow, a tests-only task, a pre-commit check, and a
  separate explicit push. Commands point at the project's own `.venv`, so
  they work whether or not a terminal has the venv activated. The commit
  task is the default build action (Ctrl+Shift+B).
* **`scripts/precommit_check.py` refuses to commit secrets, databases and
  build junk.** It blocks SQLite databases and their WAL/journal files (real
  employee and attendance data), private keys and certificate files, `.env`
  files, virtual environments, build output and caches, and scans staged text
  for private keys, Google/AWS/GitHub/Slack/Stripe credentials and database
  connection strings. The one-click commit runs it before staging anything, so
  a violation stops the commit rather than warning after the fact. Test files
  are exempt from the content scan, since Shiftora's own tests hold a fake PEM
  on purpose.
* **`scripts/one_click_commit.py` runs the guard**, and its step numbering
  now covers the extra step.

### Fixed (phone QR auto-open)

* **A phone QR built with no LAN address scanned fine and then opened
  nothing.** `phone_base_url` fell back to the placeholder host
  `this-computer`, and that placeholder was encoded straight into the printed
  QR. No phone can resolve that name, so the failure appeared only at the
  scanner, with a code that looked perfectly valid. Added
  `phone_url_for_phone()`, which refuses to build a link for a phone when
  this computer has no network address and tells the admin to join the Wi-Fi
  first. `phone_checkin_url` (the QR path) now uses it, while
  `phone_base_url` stays lenient for on-screen display in Settings, so the
  status panel keeps working offline. New `PhoneAddressError`
  (`app/phone/server.py`, exported from `app/phone`), handled with a clear
  dialog in the QR preview (`app/ui/qr_management.py`).

### Added (phone check-out)

* **Explicit Time in / Time out buttons on the phone page.** The personal
  phone page previously showed a single button whose label flipped depending
  on current status, so an employee had no way to say which one they meant
  and a mis-tap silently recorded the other action. The page now renders two
  buttons and the server honours the pressed one via a validated `action`
  field instead of inferring it from status. Files: `app/phone/server.py`
  (`do_GET` renders two forms, `do_POST` validates `action` and calls
  `record_scan`), `app/ui/qr_management.py` and `app/services/qr_service.py`
  (relabelled the per-employee QR), `tests/test_phone.py`, `README.md`. The
  service layer still rejects impossible pairs (a second time-in, a time-out
  with no session), so the buttons cannot corrupt data.
  Test with: `python -m pytest tests/test_phone.py -k "button or time_out or nonce or action"`.
* Each button gets its **own** single-use nonce, so pressing Time in does not
  spend the Time out button's nonce.
* An absent or unrecognised `action` is refused with HTTP 400 rather than
  being guessed at, so a hand-rolled POST cannot smuggle in an arbitrary
  action string.

### Not covered by the changelog

`tests/test_qr.py` is modified (the payload determinism change above) but is
not named in any changelog entry. Noted here so the audit trail is complete.

### Could not verify

* Anything Windows: `setup_windows.bat`, `installer/windows/Shiftora.iss`, the
  Inno Setup compile, the CR/LF behaviour enforced by `.gitattributes`, and the
  `tzdata`-missing crash fix on a real Windows host. Reviewed by reading only.
* `google_sheets.py` against the live Sheets API. Tests use offline fakes, so
  the request shapes and error handling are unproven against Google.
* The phone server against real phone browsers and real LAN topologies.

SPARK STATUS: DONE 2026-10-06 00:03 PST
