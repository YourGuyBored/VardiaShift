# Changelog

All notable changes to VardiaShift are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

* **Viewer role**: a read-only account type. On the Admin Account page,
  **Add account** creates an Administrator or a Viewer; a Viewer signs in
  like anybody else, sees only the dashboard and the reports, and the
  sidebar simply has no other buttons. Every write path goes through one
  check that a Viewer session fails with a clear message, so read-only
  holds even if some other door opens later. Accounts are audited on
  creation and the account list shows the role column.
  Files: `app/database/migrations.py`, `app/database/repositories.py`,
  `app/models/admin.py`, `app/services/authentication_service.py`,
  `app/context.py`, `app/ui/main_window.py`, `app/ui/admin_account.py`,
  `tests/test_viewer_role.py`, `tests/test_ui.py`, `README.md`,
  `CHANGELOG.md`.

* **Print-ready PDF reports**: the Reports page has Save PDF and Print
  buttons next to the CSV and XLSX ones. Both render the generated
  report (title, summary and table, totals row bold) through Qt's own
  PDF writer, so there is nothing extra to install and the daily,
  weekly, monthly, payroll and custom-range reports all print. Cell
  values are escaped before they reach the document.
  Files: `app/services/report_service.py`, `app/ui/reports.py`,
  `tests/test_report_pdf.py`.

* **Payroll summary export**: a new report type on the Reports page. The
  admin picks any date range - weekly, semi-monthly or monthly pay all
  come out of the same export - and gets one row per employee: days
  worked, hours in both H:MM and decimal form, approved leave days and
  late arrivals. Hours are the actually scanned time, matching how the
  dashboard treats leave. The active roster anchors the rows, and an
  employee who left mid period keeps the hours they scanned.
  Files: `app/services/report_service.py`, `app/services/attendance_service.py`,
  `app/ui/reports.py`, `tests/test_payroll.py`.

* **More dashboard charts**: the chart card now has a switcher. Alongside
  the hours-per-day bars there are two new views: Late arrivals counts the
  scans that came in past that day's schedule plus the grace period per
  day of the week (approved leave never counts), and By department shows
  the current work week's recorded hours per department, with the smaller
  departments grouping into one bar so labels stay readable. The whole
  card (title, hint, bars and totals line) changes with the switch.
  Files: `app/services/attendance_service.py`, `app/ui/dashboard.py`,
  `tests/test_lateness.py`, `tests/test_dashboard_chart.py`.

* **Leave tracking**: record approved time off per employee. A Leave button
  on the Employees page opens every day an employee is excused, along with
  the kind (sick, vacation, holiday, other) and an optional note. A leave
  day stands the schedule down completely: no Late, Early out, No show,
  Absent or short-hours flags, and nothing left to patch, while hours
  still stay true to whatever was actually scanned. On the dashboard and
  the attendance tables the day reads *On leave (Vacation)*, and the
  tardiness report does the same, listing the day without any owed hours.
  Every entry and removal is audited. Files: `app/models/leave.py`,
  `app/services/leave_service.py`, `app/ui/leave_dialog.py`,
  `tests/test_leave.py`.

* **Shifts**: give a group of employees their own work times. Shifts are
  named schedules (a start, an end, and the days they cover) managed on a
  new Shifts page, and assigned on the employee form; anyone left on the
  organisation shift keeps the times set in Settings, as before. The
  dashboard and the attendance tables now carry a Schedule column showing
  Late, Early out, No show or Day off against that day's schedule, using
  the same grace period the tardiness report already had, and that report
  now works shift by shift: day rows on an assigned day off show as "Day
  off" and cost nothing to patch, while an absence on a scheduled day
  lists that shift's full hours. Employees without an assignment see no
  change at all. Files: `app/database/migrations.py`,
  `app/database/repositories.py`, `app/models/shift.py`,
  `app/services/shift_service.py`, `app/services/attendance_service.py`,
  `app/services/report_service.py`, `app/ui/shifts_view.py`,
  `tests/test_shifts.py`, `tests/test_shift_schedule.py`.

* **Auto time-out**: close forgotten sessions at a time you pick. When the
  switch in Settings -> Attendance is on, a session that is still open at
  *Auto time-out at* (default 23:59) is closed with that moment recorded as
  the time-out, and labelled *Auto time-out* on the dashboard, in the
  attendance table and in reports so you can review it. Until now a
  forgotten session froze that employee until an administrator closed it
  by hand; now the app clears it on its own the next time anyone scans or
  opens the dashboard. Every closure is audited (credited to "system",
  because no person decided it). A session clocked in after the cutoff
  (an overnight session, or a night shift) is cut off the next day at the
  same time instead of the same night. This replaces the old "Auto-close
  after N hours" rule, which was written but never wired to anything;
  existing databases are not affected because it had never run. Files:
  `app/models/settings.py`, `app/services/attendance_service.py`,
  `tests/test_attendance.py`.

* Phone check-in can now ask for a **personal PIN**. The administrator gives
  each employee a 4 to 8 digit PIN on the Employees page, and when Settings
  says require it, the Time in and Time out buttons only appear after the
  PIN is typed right. PINs are stored the way admin passwords are (a PBKDF2
  hash, never the PIN itself) and the PIN is never written to the audit log.
  Wrong PINs lock that employee out of phone check-in for a few minutes,
  counted both per employee and per device, and every wrong attempt is
  logged as a failed phone scan. Files: `app/phone/server.py`,
  `app/services/employee_service.py`, `app/database/repositories.py`,
  `app/ui/employee_management.py`, `tests/test_phone.py`,
  `tests/test_employees.py`, `tests/test_ui.py`.
* **Allowed networks** in Settings limits check-in to trusted Wi-Fi. List
  networks the way the router writes them (`192.168.1.0/24`), several
  comma-separated, and phones from anywhere else are refused before any
  page is served; leave it empty and everything on the local network that
  can reach the computer is allowed, as before. The Phone tab in Settings
  offers a **Use this computer's network** button that pre-fills the field
  with this machine's own subnet, so restricting check-in to the office
  Wi-Fi is one click plus Save. Files: `app/phone/server.py`,
  `app/services/settings_service.py`, `app/ui/settings.py`,
  `app/utils/validation.py`, `tests/test_phone.py`, `tests/test_ui.py`.
* Schema version 7 adds a nullable `phone_pin_hash` column to employees.
  Existing databases migrate in place and keep all of their data; a fresh
  install includes the column from the start. Files: `app/database/migrations.py`,
  `tests/test_employees.py`.

### Changed

* The README gained a Roadmap section listing what is being built next, and
  the repository page now states in one line what the app is (the GitHub
  description was empty). Files: `README.md`.

## [1.4.0] - 2026-10-16

### Added

* Phone attendance now offers a one-click **Allow phones through the firewall**
  button in Settings. It detects the host firewall (Windows Defender Firewall,
  or ufw/firewalld on Linux), says plainly whether the check-in port is already
  reachable from the local network, and - only when you press it - asks the
  operating system for one inbound exception scoped to the check-in port and
  the local subnet. There is no silent escalation, no UPnP, and no router
  port-forwarding; the OS prompt is always yours to decline. A **Remove
  firewall rule** button takes the exception back out. Files:
  `app/phone/firewall.py`, `app/phone/__init__.py`, `app/ui/settings.py`,
  `tests/test_firewall.py`, `tests/test_ui.py`.

### Changed

* Version bumped to `1.4.0` in `APP_VERSION`, `pyproject.toml` and the installer
  default, so the tag, the footer the app draws and the installer all agree.
* The download is about 85 MB heavier once installed: OpenCV and numpy are part
  of the app now rather than an optional extra, and that is what makes webcam
  scanning work out of the box. The headless OpenCV wheel is the smallest form
  of it and needs no libGL on Linux. Files: `requirements.txt`,
  `VardiaShift.spec`, `pyproject.toml`.
* Settings form fields no longer stretch across the whole window - a two-line
  text box was 900px wide on a 1360px window. They stop at a readable width and
  stay left-aligned under their labels. Files: `app/ui/settings.py`.
* Panels that had drifted onto an 8-12px corner radius - the QR preview, the QR
  step list and the report summary strip - now use the same hard edges as every
  other surface. Files: `app/ui/qr_management.py`, `app/ui/reports.py`.
* A status column is now sized to the widest pill it can show rather than to a
  fixed guess. The column also stays put as the day's attendance changes, so it
  no longer shifts under the reader. Files: `app/ui/widgets.py`,
  `app/ui/dashboard.py`, `app/ui/attendance_view.py`,
  `app/ui/employee_management.py`.
* Table headers ellipsize when a table is narrow ("Empl...") instead of being
  sliced mid-word ("nployee"), which is what Qt does until it is told to elide.
  Files: `app/ui/widgets.py`, `app/ui/admin_account.py`,
  `app/ui/attendance_view.py`, `app/ui/dashboard.py`,
  `app/ui/employee_management.py`, `app/ui/qr_management.py`,
  `app/ui/report_dialogs.py`, `app/ui/reports.py`, `app/ui/settings.py`.
* Screenshots in the README were re-rendered, and the new Settings -> Phone
  screen joined the gallery. The dashboard, Employees and Attendance shots were
  refreshed to show the status pills reading in full. The kiosk shot now shows
  the camera controls working rather than "Camera unavailable" - the bug the
  old shot had been quietly documenting. The README now names three Settings
  tabs the way the tab bar labels them - Kiosk, Phone and Sheets - instead of
  by their longer internal group names. Files:
  `assets/screenshots/`, `scripts/shoot_ui.py`, `README.md`.

### Fixed

* **Webcam scanning never worked in a packaged build, which is why the kiosk
  offered no camera at all.** `opencv-python` was declared an optional extra,
  so `pip install -r requirements.txt` never installed it and PyInstaller had
  nothing to bundle - and the build spec excluded `numpy` as well, which
  OpenCV cannot import without, so bundling OpenCV alone would not have been
  enough either. OpenCV is now an ordinary dependency (the headless wheel,
  which needs no libGL on Linux) and the spec keeps numpy. Files:
  `requirements.txt`, `VardiaShift.spec`, `pyproject.toml`,
  `requirements-optional.txt` (removed).
* **The scanner offered cameras that were not there.** `_open_capture()`
  documented that "a frame read is the only honest test" and then only asked
  `isOpened()`, which some backends report for an index with nothing behind
  it. Auto-detect could pick one of those, announce "Camera 0 started", and
  die a second later with "the camera stopped sending frames". A probe now
  waits for a real frame and hands the device back if none arrives, bounded by
  `PROBE_TIMEOUT_MS` - a constant that was defined and never used. Files:
  `app/qr/scanner.py`.
* **The kiosk window would not appear until the camera search had finished.**
  Probing opens every candidate device, and a real webcam takes the better
  part of a second to answer, so the window was held back by a second or more -
  worse the more cameras were plugged in. The search runs in the background
  now and fills the picker when it lands; closing the kiosk waits for it to
  stop. Files: `app/ui/attendance_kiosk.py`, `tests/test_camera.py`.
* **"Start camera" appeared to do nothing for almost two seconds.** Opening a
  device and waiting for its first frame takes that long (measured: 1.79s),
  and the button kept its old label until the camera answered. The click shows
  a wait cursor now. Files: `app/ui/attendance_kiosk.py`.
* **Two Settings tabs, and the QR Codes page, were taller than the window, and
  Qt answered by drawing the lower rows on top of the ones above them.** Every
  Settings tab and every QR Codes tab now scrolls, the way the first-run window
  already did. Files: `app/ui/settings.py`, `app/ui/qr_management.py`.
* **The Reports toolbar showed an unlabelled date box next to a stray "From"
  and "To".** Each control is labelled and only appears when the chosen report
  type uses it, and the toolbar now applies the type on first load rather than
  only when you change it. Files: `app/ui/reports.py`.
* The Backup tab's database summary was a read-only text box whose own minimum
  height was taller than the box it was given, so the last row was drawn cut in
  half. It is a label now. Files: `app/ui/settings.py`.
* The QR preview's payload was squeezed into a text box in the same way and drew
  half cut off, and its white plate stretched the full width of the card. Files:
  `app/ui/qr_management.py`.
* The attendance kiosk showed a literal `00:00` until its clock ticked a second
  later. Files: `app/ui/attendance_kiosk.py`.
* Four labels asked for the monospace text style by object name, which no rule
  in the stylesheet matches, so they silently kept the body font. They now set
  the `role` property the stylesheet actually keys on, which lines up the
  Backup tab's database summary and the QR payload. Files:
  `app/ui/settings.py`, `app/ui/qr_management.py`, `app/ui/admin_account.py`,
  `app/ui/attendance_kiosk.py`.
* The icon integration test compared a Pillow-compressed PNG byte for byte, and
  the launcher test read a POSIX mode bit on Windows, so both failed on the
  Windows runner while passing on Linux. The icon is now compared by layout and
  pixels, and the execute bit is read from the git index off POSIX. Test-only;
  the application is unchanged. Files: `tests/test_desktop_integration.py`.
* **The dashboard's seven status tiles overlapped at the window's minimum size,
  and the last one was cut off at the edge.** Every tile asked for a 150px
  minimum, so the row wanted 1174px in a window that can only offer it 892. A
  tile now takes the width its own content needs, and the row fits at every
  window size. Files: `app/ui/widgets.py`.
* **The "Missing Time Out" pill lost characters off both ends, reading as
  "lissing Time Ou" on the dashboard and Attendance.** A cell widget is laid out
  inside the cell's own padding, and the pill was inset a second time on top of
  that, which left it narrower than the label it had to show. Files:
  `app/ui/widgets.py`, `app/ui/dashboard.py`, `app/ui/attendance_view.py`,
  `app/ui/employee_management.py`.
* **The Administrator accounts table showed two "Active" pills on the same
  row.** The page repopulates each time it is shown, and `setCellWidget` does
  not delete the widget it replaces, so the earlier pill stayed on screen
  underneath the new one. Files: `app/ui/admin_account.py`.
* At the window's minimum size the dashboard's weekly chart and the summary
  line under it were drawn on top of each other. The chart can now give up some
  height before that happens. Files: `app/ui/widgets.py`,
  `tests/test_dashboard_chart.py`.

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
