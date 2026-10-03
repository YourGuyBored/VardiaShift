<div align="center">

# Shiftora

**Standalone desktop employee time-in / time-out & attendance management**

No servers. No cloud. No Python required to use it.

Download it, open it, scan QR codes, track hours.

[![tests](https://github.com/YOUR-USERNAME/shiftora/actions/workflows/tests.yml/badge.svg)](https://github.com/YOUR-USERNAME/shiftora/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

![Shiftora dashboard](assets/screenshots/dashboard.png)

</div>

---

## What is Shiftora?

Shiftora is a **standalone desktop application** for small teams and offices
that need simple, reliable attendance tracking:

* Employees scan a **personal QR code**, then a **TIME IN** / **TIME OUT** code.
* The app records exact arrival/departure times and computes hours worked.
* Administrators see who is working, weekly progress against an hour goal,
  attendance history, reports, and backups - all offline.

Everything is stored in a local **SQLite** database that the app creates and
manages itself. There is nothing to install, configure, or host.

---

## Download (normal users start here)

You do **not** need Python or any technical setup.

1. Go to the repository's **Releases** page (`Releases` on the right sidebar).
2. Download the latest release for your system:
   * Windows: **`Shiftora-Windows-x64.zip`**
   * Linux: **`Shiftora-Linux-x64.tar.gz`**
3. **Extract** the archive anywhere you like.
4. Open **`Shiftora.exe`** (Windows) or **`Shiftora`** (Linux).
5. That's it - the app starts and creates its own data folder automatically.

> Your data lives in a per-user folder, never next to the executable:
> `%LOCALAPPDATA%\Shiftora` on Windows,
> `~/Library/Application Support/Shiftora` on macOS,
> `~/.local/share/Shiftora` on Linux.

---

## First launch

The very first time Shiftora opens, it detects that no database exists,
creates one, and shows the **first-time setup** screen:

```text
================================
     EMPLOYEE ATTENDANCE
================================

        FIRST-TIME SETUP

Create Administrator Account

Username
[________________]

Password (min. 8 characters)
[________________]

Confirm Password
[________________]

        [ CREATE ACCOUNT ]
```

After creating the account you land on the **dashboard**. You will sign in
with this account on every later launch.

Passwords are stored only as salted **PBKDF2-SHA256** hashes - never in plain
text. After several wrong attempts sign-in locks briefly, and an idle session
signs itself out (configurable in Settings).

---

## Adding employees

Open **Employees** → **Add Employee** and fill in:

| Field          | Example              |
|----------------|----------------------|
| Employee ID    | `EMP-001` (suggested automatically) |
| Full Name      | Juan Dela Cruz       |
| Department     | IT                   |
| Position       | Student Assistant    |
| Weekly goal    | Organisation default, or e.g. 20 hours |

Employees are listed with their status (**Active** / **Inactive**), date added
and weekly goal. You can **edit**, **deactivate/reactivate**, and search them.

Employees with attendance history are **never permanently deleted** -
deactivate them instead, so the records stay intact.

---

## QR setup

Open the **QR Codes** page. There are three kinds of code:

1. **Employee QR** - one personal code per employee. Print one card for each
   person (single, or all at once). Each card carries only a random token,
   never a name or ID number.
2. **TIME IN QR** - the public code posted at the entrance for arrivals.
3. **TIME OUT QR** - the public code posted at the entrance for departures.

For each code you can **generate**, **preview**, **download as PNG** and
**print** a labelled sheet. If a card is lost or you suspect misuse, press
**Regenerate** - the old code stops working immediately and the change is
written to the audit log.

### Why two scans?

The public TIME IN / TIME OUT codes carry **no employee information**, so
nobody can clock in on someone else's behalf. Attendance is only recorded
when the employee's *own* QR is scanned first:

```text
Employee QR  +  TIME IN QR   =  Time In recorded
Employee QR  +  TIME OUT QR  =  Time Out recorded
```

---

## Employee usage (the kiosk)

Open the **Attendance Kiosk** from the sidebar (or press the kiosk button).
It is a deliberately simple full-screen screen with a live clock:

```text
================================

       COMPANY ATTENDANCE

             09:02 AM
        October 3, 2026

       [ SCAN QR CODE ]

   Scan your employee QR code

================================
```

**Arriving:**

1. Scan your personal employee QR.
2. The kiosk greets you by name.
3. Scan the **TIME IN** code.

```text
TIME IN SUCCESSFUL

Juan Dela Cruz

09:02 AM
October 3, 2026

Have a productive day!
```

**Leaving:**

1. Scan your personal employee QR.
2. Scan the **TIME OUT** code.

```text
TIME OUT SUCCESSFUL

Juan Dela Cruz

05:14 PM

Today's Work Time
8h 12m
```

Mistakes are explained in plain language (`Already Timed In`, `Not Timed In`,
`Duplicate Scan Ignored`, ...).

![Attendance kiosk](assets/screenshots/kiosk.png)

### Scanning hardware

* **Webcam** - the kiosk decodes the camera feed directly (needs the optional
  `opencv-python` package in a from-source install; release builds document
  whether it is included).
* **USB QR reader** - any keyboard-style scanner just works: scan, press
  Enter, done. No drivers or configuration.
* **Manual entry** - an employee ID can be typed when a scanner is unavailable
  (can be disabled in Settings → Attendance; manual entries are labelled and
  audited).

---

## Administrator workflow

**Dashboard** - who is working right now, who timed out, who is missing a
time-out, today's hours, this week's hours vs the organisation goal, and a
live per-employee table with search and status filters.

![Employee management](assets/screenshots/employees.png)

**Employee details** - pick an employee to see weekly progress
(`24h 35m / 30h`, remaining, overtime, progress bar), a day-by-day breakdown,
and complete history with Today / This week / Last week / This month /
Custom-range filters.

**Corrections** - forgot to scan out? Add or fix times with a required reason.
The original values stay in the **audit log** with your username, old value,
new value and reason. Nothing is ever silently overwritten.

**Reports** - daily, weekly, monthly and custom-range reports, optionally per
employee, exported as **CSV** (always) or **XLSX**.

**Settings** - organisation name, time zone, date/time formats, default
weekly goal (20/25/30/35/40 presets), work-week days, shift times, daily cap,
overtime tracking, grace periods, duplicate-scan window, kiosk behaviour,
auto sign-out, and audit retention. Everything persists in the database.

**Backup & Restore** - one-click timestamped backups
(`backup_2026-10-03_21-30-00.db`), a backup list, restore from the list or
from a file, automatic verification before restoring, and an automatic safety
copy of the current database first. Restoring signs you out so you sign back
in against the restored data.

---

## Developer installation

```bash
git clone https://github.com/YOUR-USERNAME/shiftora.git
cd shiftora
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python run.py
```

Optional extras:

```bash
pip install -r requirements-optional.txt   # webcam scanning (opencv)
```

Run the test suite (303 tests: services, QR, reports, backup, GUI):

```bash
python -m pytest tests/ -q
```

Headless environments (CI, servers) work out of the box - the suite defaults
to Qt's offscreen platform. To *watch* the GUI tests on a machine with a
display:

```bash
QT_QPA_PLATFORM=xcb python -m pytest tests/test_ui.py
```

---

## Build (create the downloadable executable)

**Windows** (on a Windows machine) - double-click or run:

```bat
build_windows.bat
```

**Linux**:

```bash
./build_linux.sh
```

Or directly:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm Shiftora.spec
```

The distributable appears under `dist/`:

```text
GitHub
   ↓  Releases
Shiftora-Windows-x64.zip
   ↓  Download & Extract
Shiftora.exe
   ↓  Run (no Python needed)
```

Tagged pushes (`v*`) automatically build both packages and publish a GitHub
release via `.github/workflows/release.yml`. Every push also runs the full
test suite on Windows and Linux via `.github/workflows/tests.yml`.

---

## Project structure

```text
shiftora/
├── app/
│   ├── main.py               # entry point, setup→login→main state machine
│   ├── context.py            # composition root (database, services, QR)
│   ├── constants.py
│   ├── database/             # SQLite connection, migrations, repositories
│   ├── models/               # admin, employee, attendance, settings, QR, audit
│   ├── services/             # auth, employees, attendance, reports, backup, QR, settings
│   ├── qr/                   # payload format, QR/card image generation, scanner widget
│   ├── ui/                   # setup, login, dashboard, employees, attendance,
│   │                         # kiosk, QR management, reports, settings, admin
│   └── utils/                # app-data paths, time utils, validation
├── tests/                    # 295 pytest tests (services, QR, reports, DB, UI)
├── assets/                   # application icon
├── data/                     # placeholder (runtime data lives in the OS data dir)
├── run.py                    # `python run.py` launcher
├── Shiftora.spec             # PyInstaller specification
├── build_windows.bat / build_linux.sh
├── requirements*.txt / pyproject.toml
└── README.md / CHANGELOG.md / LICENSE
```

The service layer never touches Qt and the UI never touches SQL directly, so
a future cloud-sync feature can be added at the `ApplicationContext` level
without rewriting screens or queries.

---

## Security

* PBKDF2-HMAC-SHA256 password hashing (390 000 iterations), per-password salt.
* QR payloads contain only opaque random tokens - no names, IDs or personal
  data. Tokens are revocable individually.
* Parameterised SQL everywhere; destructive restores always take a safety copy.
* Admin-only configuration, session handling with auto sign-out.
* Full audit log for sign-ins, employee changes, corrections, QR rotations,
  settings, backups and restores.

---

## Offline-first

After installation Shiftora works with **no internet connection**. The only
things that need the network are downloading the app itself and (optionally)
receiving updates.

---

## License

MIT - see [LICENSE](LICENSE).
