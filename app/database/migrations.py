"""Schema creation and versioned migrations.

``SCHEMA_VERSION`` is stored in ``app_meta``.  On start-up
:func:`migrate` creates any missing table/index and then walks every version in
``MIGRATIONS`` exactly once, in order.
"""

from __future__ import annotations

from app.constants import APP_VERSION
from app.database.database import Database, utc_now

SCHEMA_VERSION = 6

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    admin_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT NOT NULL DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_login_at   TEXT
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_code    TEXT NOT NULL UNIQUE,
    full_name        TEXT NOT NULL,
    department       TEXT NOT NULL DEFAULT '',
    position         TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    weekly_goal_hours INTEGER,
    badge_code       TEXT,
    qr_token         TEXT NOT NULL UNIQUE,
    date_added       TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    deactivated_at   TEXT,
    deactivated_by   TEXT
);

CREATE INDEX IF NOT EXISTS idx_employees_status ON employees (status);
CREATE INDEX IF NOT EXISTS idx_employees_name ON employees (full_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_badge
    ON employees (badge_code COLLATE NOCASE) WHERE badge_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS attendance (
    attendance_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id      INTEGER NOT NULL,
    work_date        TEXT NOT NULL,
    time_in          TEXT,
    time_out         TEXT,
    duration_minutes INTEGER,
    status           TEXT NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open', 'closed', 'missing')),
    source           TEXT NOT NULL DEFAULT 'qr'
                      CHECK (source IN ('qr', 'manual', 'auto', 'correction', 'phone')),
    is_corrected     INTEGER NOT NULL DEFAULT 0 CHECK (is_corrected IN (0, 1)),
    note             TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    corrected_by     TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees (employee_id) ON DELETE RESTRICT,
    UNIQUE (employee_id, work_date)
);

CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance (work_date);
CREATE INDEX IF NOT EXISTS idx_attendance_status ON attendance (status);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS qr_tokens (
    token_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    token       TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL CHECK (kind IN ('employee', 'time_in', 'time_out')),
    label       TEXT NOT NULL DEFAULT '',
    employee_id INTEGER,
    version     INTEGER NOT NULL DEFAULT 1,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees (employee_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_qr_tokens_kind ON qr_tokens (kind);
CREATE INDEX IF NOT EXISTS idx_qr_tokens_employee ON qr_tokens (employee_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_username TEXT NOT NULL DEFAULT 'system',
    action         TEXT NOT NULL,
    entity_type    TEXT NOT NULL DEFAULT '',
    entity_id      TEXT,
    description    TEXT NOT NULL DEFAULT '',
    old_value      TEXT NOT NULL DEFAULT '',
    new_value      TEXT NOT NULL DEFAULT '',
    reason         TEXT NOT NULL DEFAULT '',
    severity       TEXT NOT NULL DEFAULT 'info'
                   CHECK (severity IN ('info', 'warning', 'critical')),
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs (action);

CREATE TABLE IF NOT EXISTS scan_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    employee_id INTEGER,
    payload     TEXT NOT NULL DEFAULT '',
    accepted    INTEGER NOT NULL DEFAULT 1,
    result      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scan_events_created ON scan_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_events_token ON scan_events (token_hash);
"""

# Ordered list of (version, [statements]).  Each entry runs exactly once.
MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            """ALTER TABLE attendance ADD COLUMN source TEXT NOT NULL DEFAULT 'qr'""",
        ],
    ),
    (
        2,
        [
            """ALTER TABLE attendance ADD COLUMN is_corrected INTEGER NOT NULL DEFAULT 0""",
            """ALTER TABLE attendance ADD COLUMN corrected_by TEXT""",
        ],
    ),
    (
        3,
        [
            """ALTER TABLE employees ADD COLUMN deactivated_at TEXT""",
            """ALTER TABLE employees ADD COLUMN deactivated_by TEXT""",
        ],
    ),
    (
        4,
        [
            # Scans are only "duplicates" when they target the same working day.
            """ALTER TABLE scan_events ADD COLUMN work_date TEXT NOT NULL DEFAULT ''""",
        ],
    ),
    (
        5,
        [
            # Widen the attendance source list ('phone') and guard durations.
            # SQLite cannot alter a CHECK in place, so the table is rebuilt;
            # every row is copied over unchanged. No foreign-key juggling is
            # needed: nothing else references attendance, and copied rows
            # already satisfy the employee relationship.
            """CREATE TABLE attendance_new (
                attendance_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id      INTEGER NOT NULL,
                work_date        TEXT NOT NULL,
                time_in          TEXT,
                time_out         TEXT,
                duration_minutes INTEGER
                                 CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
                status           TEXT NOT NULL DEFAULT 'open'
                                 CHECK (status IN ('open', 'closed', 'missing')),
                source           TEXT NOT NULL DEFAULT 'qr'
                                 CHECK (source IN ('qr', 'manual', 'auto', 'correction', 'phone')),
                is_corrected     INTEGER NOT NULL DEFAULT 0 CHECK (is_corrected IN (0, 1)),
                note             TEXT NOT NULL DEFAULT '',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                corrected_by     TEXT,
                FOREIGN KEY (employee_id) REFERENCES employees (employee_id) ON DELETE RESTRICT,
                UNIQUE (employee_id, work_date)
            )""",
            """INSERT INTO attendance_new (
                attendance_id, employee_id, work_date, time_in, time_out,
                duration_minutes, status, source, is_corrected, note,
                created_at, updated_at, corrected_by
            ) SELECT
                attendance_id, employee_id, work_date, time_in, time_out,
                duration_minutes, status, source, is_corrected, note,
                created_at, updated_at, corrected_by
            FROM attendance""",
            """DROP TABLE attendance""",
            """ALTER TABLE attendance_new RENAME TO attendance""",
            """CREATE INDEX idx_attendance_date ON attendance (work_date)""",
            """CREATE INDEX idx_attendance_status ON attendance (status)""",
            """CREATE INDEX IF NOT EXISTS idx_scan_events_token
               ON scan_events (token_hash)""",
        ],
    ),
    (
        6,
        [
            # Optional human-typed identifier per employee (badge number, short
            # code). Nullable so existing rows are untouched; the partial
            # unique index only constrains rows that actually set one.
            """ALTER TABLE employees ADD COLUMN badge_code TEXT""",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_badge
               ON employees (badge_code COLLATE NOCASE) WHERE badge_code IS NOT NULL""",
        ],
    ),
]

LATEST_VERSION = max(version for version, _ in MIGRATIONS)


def get_meta(db: Database, key: str, default: str = "") -> str:
    row = db.query_one("SELECT value FROM app_meta WHERE key = ?", (key,))
    return row["value"] if row else default


def set_meta(db: Database, key: str, value: str) -> None:
    db.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def current_version(db: Database) -> int:
    raw = get_meta(db, "schema_version", "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def initialize(db: Database) -> None:
    """Create the base schema (idempotent)."""
    db.executescript(BASE_SCHEMA)
    set_meta(db, "schema_version", str(SCHEMA_VERSION))
    if not get_meta(db, "installed_at"):
        set_meta(db, "installed_at", utc_now())


def migrate(db: Database) -> int:
    """Apply pending migrations, returning the resulting schema version."""
    db.executescript(BASE_SCHEMA)

    version = current_version(db)
    if version == 0:
        # First launch on this machine: stamp the install time.
        set_meta(db, "installed_at", utc_now())
    for target, statements in MIGRATIONS:
        if version >= target:
            continue
        for statement in statements:
            try:
                db.execute(statement)
            except Exception as exc:  # pragma: no cover - defensive
                message = str(exc).lower()
                # Adding an existing column is not an error: another install may
                # have created it via BASE_SCHEMA.
                if "duplicate column" in message or "already exists" in message:
                    continue
                raise
        version = target
        set_meta(db, "schema_version", str(version))

    set_meta(db, "schema_version", str(SCHEMA_VERSION))
    set_meta(db, "app_version", APP_VERSION)
    return SCHEMA_VERSION