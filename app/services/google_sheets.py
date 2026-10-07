"""Optional Google Sheets export.

Sends a generated report to a Google Sheet as a new tab, so attendance data
can live next to anything else the organisation keeps in Google Sheets.

This is deliberately optional and offline-safe:

* The client libraries ship with VardiaShift, but every entry point still
  degrades gracefully when they are missing instead of crashing, and all
  local features keep working.
* Authentication uses a Google Cloud **service account** key file chosen by
  the administrator. The file is validated and copied into the application
  data folder; its contents are never logged or committed.
* Setup on the Google side (once): create a service account, download its
  JSON key, share the target spreadsheet with the service account's email
  as Editor. Steps are in the README.

Nothing here runs at startup and nothing phones home unless the
administrator presses "Send to Google Sheets".
"""

from __future__ import annotations

import json
from pathlib import Path

SERVICE_ACCOUNT_FILENAME = "google_service_account.json"
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_REQUIRED_KEY_FIELDS = ("type", "project_id", "private_key_id", "private_key",
                        "client_email", "client_id")


class GoogleSheetsError(Exception):
    """User-facing failure sending to Google Sheets."""

    def __init__(self, message: str, code: str = "sheets_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def sheets_available() -> bool:
    """Whether the optional Google client libraries are installed."""
    try:
        import google.auth  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
    except ImportError:
        return False
    return True


def _require_libraries() -> None:
    if not sheets_available():
        raise GoogleSheetsError(
            "Google Sheets support is not available in this install. "
            "Reinstall from requirements.txt or use a release build.",
            "not_installed",
        )


def validate_service_account_file(path: Path | str) -> dict:
    """Read and sanity-check a service-account key file.

    Returns the parsed JSON on success. Raises GoogleSheetsError otherwise.
    The key material itself is never included in any message or log.
    """
    source = Path(path)
    if not source.is_file():
        raise GoogleSheetsError(
            f"Service account file not found: {source}", "missing_file"
        )
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GoogleSheetsError(
            f"That file is not valid JSON: {exc}", "bad_file"
        ) from exc
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise GoogleSheetsError(
            "That is not a service-account key file (expected "
            '"type": "service_account").',
            "bad_file",
        )
    missing = [key for key in _REQUIRED_KEY_FIELDS if not data.get(key)]
    if missing:
        raise GoogleSheetsError(
            "The key file is missing fields: " + ", ".join(missing),
            "bad_file",
        )
    return data


def stored_key_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / SERVICE_ACCOUNT_FILENAME


def store_service_account_file(source: Path | str, data_dir: Path | str) -> Path:
    """Validate a key file and copy it into the application data folder."""
    validate_service_account_file(source)
    destination = stored_key_path(data_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(Path(source).read_bytes())
    return destination


def key_status(data_dir: Path | str) -> tuple[str, str]:
    """Short status for the settings screen: (state, detail)."""
    path = stored_key_path(data_dir)
    if not path.is_file():
        return "missing", "No service account file chosen yet."
    try:
        data = validate_service_account_file(path)
    except GoogleSheetsError as exc:
        return "invalid", exc.message
    return "ok", f"Linked service account: {data['client_email']}"


def build_sheet_values(report) -> list[list]:
    """Flatten a ReportResult into plain rows for the Sheets API.

    Cells go through the same formula-injection sanitiser as the CSV/XLSX
    exports, stringified so the API always receives strings.
    """
    from app.services.report_service import sanitize_spreadsheet_cell

    def cell(value) -> str:
        clean = sanitize_spreadsheet_cell(value)
        return "" if clean is None else str(clean)

    rows = [[report.title], [report.subtitle], []]
    for label, value in report.summary:
        rows.append([cell(label), cell(value)])
    rows.append([])
    rows.append([cell(header) for header in report.headers])
    for record in report.rows:
        rows.append([cell(item) for item in record])
    if report.totals:
        rows.append([])
        rows.append([cell(item) for item in report.totals])
    return rows


def sheet_title_for(report, stamp: str) -> str:
    """Tab name for this upload. Sheets tab names cap at 100 characters."""
    base = f"{report.title} {stamp}".strip()
    return base[:100] if len(base) > 100 else base


def _service(key_file: Path | str):
    _require_libraries()
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_service_account_file(
        str(key_file), scopes=_SCOPES
    )
    return build("sheets", "v4", credentials=credentials)


def push_report(
    key_file: Path | str,
    spreadsheet_id: str,
    report,
    stamp: str,
    service=None,
) -> tuple[str, int]:
    """Upload a report as a new tab. Returns (tab title, rows written).

    ``service`` is an injectable stand-in for the discovery client so tests
    never touch the network.
    """
    spreadsheet = (spreadsheet_id or "").strip()
    if not spreadsheet:
        raise GoogleSheetsError(
            "Enter the spreadsheet ID in Settings → Google Sheets first.",
            "no_spreadsheet",
        )
    if report is None or report.is_empty:
        raise GoogleSheetsError("Generate a report first.", "empty_report")
    if service is None:
        validate_service_account_file(key_file)
        service = _service(key_file)

    title = sheet_title_for(report, stamp)
    values = build_sheet_values(report)
    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        ).execute()
    except Exception as exc:
        if "already exists" not in str(exc):
            raise GoogleSheetsError(
                f"Google Sheets refused the upload: {exc}", "api_error"
            ) from exc
    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet,
            range=f"'{title}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()
    except Exception as exc:
        raise GoogleSheetsError(
            f"Google Sheets refused the upload: {exc}", "api_error"
        ) from exc
    return title, len(values)


def verify_connection(
    key_file: Path | str,
    spreadsheet_id: str,
    service=None,
) -> str:
    """Verify that the key is valid and the target spreadsheet is reachable.

    Returns the title of the spreadsheet on success. Raises GoogleSheetsError
    with an actionable message on failure.
    """
    spreadsheet = (spreadsheet_id or "").strip()
    if not spreadsheet:
        raise GoogleSheetsError(
            "Enter the spreadsheet ID in Settings → Google Sheets first.",
            "no_spreadsheet",
        )
    if service is None:
        validate_service_account_file(key_file)
        service = _service(key_file)

    try:
        sheet_meta = service.spreadsheets().get(spreadsheetId=spreadsheet).execute()
        props = sheet_meta.get("properties") or {}
        return props.get("title") or spreadsheet
    except GoogleSheetsError:
        raise
    except Exception as exc:
        raise GoogleSheetsError(
            f"Could not connect to Google Sheets ({exc}). "
            "Check the spreadsheet ID and ensure the spreadsheet is shared "
            "with the service account as Editor.",
            "api_error",
        ) from exc


# Prevent pytest from collecting this helper if imported in test files
verify_connection.__test__ = False  # type: ignore[attr-defined]


__all__ = [
    "GoogleSheetsError",
    "SERVICE_ACCOUNT_FILENAME",
    "build_sheet_values",
    "key_status",
    "push_report",
    "sheet_title_for",
    "sheets_available",
    "store_service_account_file",
    "stored_key_path",
    "validate_service_account_file",
    "verify_connection",
]