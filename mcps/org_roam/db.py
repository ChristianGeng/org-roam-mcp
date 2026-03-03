"""SQLite connection and org-roam database detection."""

import os
import sqlite3
import subprocess
from pathlib import Path


REQUIRED_TABLES = {"files", "nodes"}
EMACS_DB_LOCATION_EVAL = (
    "(progn "
    "(require 'org-roam nil t) "
    "(let ((loc (cond "
    "((fboundp 'org-roam-db-location) (org-roam-db-location)) "
    "((boundp 'org-roam-db-location) org-roam-db-location) "
    "(t nil)))) "
    "(when loc (princ loc))))"
)


def _extract_db_path(raw_output: str) -> str | None:
    """Extract a potential database path from emacsclient output."""
    if not raw_output:
        return None

    for line in reversed(raw_output.splitlines()):
        candidate = line.strip().strip('"')
        if not candidate or candidate == "nil":
            continue
        if candidate.endswith(".db"):
            return candidate

    candidate = raw_output.strip().strip('"')
    if candidate and candidate != "nil" and candidate.endswith(".db"):
        return candidate

    return None


def _is_valid_roam_db(db_path: Path) -> bool:
    """Check whether a SQLite file looks like a usable org-roam DB."""
    if not db_path.is_file():
        return False

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
    except sqlite3.Error:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return REQUIRED_TABLES.issubset(tables)


def _server_file_candidates() -> list[str]:
    """Return likely Emacs server socket locations for the current user."""
    uid = os.getuid()
    return [
        f"/run/user/{uid}/emacs/server",
        f"/tmp/emacs{uid}/server",
    ]


def _detect_db_from_server(server_file: str | None = None) -> str | None:
    """Try to detect org-roam DB path via emacsclient against a server."""
    command = ["emacsclient"]
    if server_file:
        command.extend(["--server-file", server_file])
    command.extend(["--eval", EMACS_DB_LOCATION_EVAL])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    detected_path = _extract_db_path(result.stdout)
    if not detected_path:
        return None

    candidate = Path(detected_path).expanduser()
    if _is_valid_roam_db(candidate):
        return str(candidate)

    return None


def detect_db() -> str:
    """Locate the org-roam SQLite database.

    Detection order:
    1. Emacs server introspection via emacsclient
    2. ORG_ROAM_DB environment variable
    3. Common filesystem locations
    """
    for server_file in [None, *_server_file_candidates()]:
        server_db = _detect_db_from_server(server_file)
        if server_db:
            return server_db

    env_db = os.environ.get("ORG_ROAM_DB")
    if env_db:
        env_path = Path(env_db).expanduser()
        if _is_valid_roam_db(env_path):
            return str(env_path)

    home = Path.home()
    candidates = [
        home / "emacs-conf" / "org-roam.db",
        home / "doom-emacs" / ".local" / "cache" / "org-roam.db",
        home / ".emacs.d" / "org-roam.db",
        home / ".emacs.d" / ".local" / "cache" / "org-roam.db",
        home / ".config" / "emacs" / "org-roam.db",
        home / ".local" / "share" / "emacs" / "org-roam.db",
    ]
    for loc in candidates:
        if _is_valid_roam_db(loc):
            return str(loc)

    raise FileNotFoundError(
        "org-roam.db not found via Emacs server, ORG_ROAM_DB, or known locations."
    )


def get_connection() -> sqlite3.Connection:
    """Return a read-only SQLite connection to the org-roam database."""
    db_path = detect_db()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _strip_elisp_quotes(value):
    """Strip Elisp-style surrounding double quotes from string values."""
    if isinstance(value, str) and len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def quote_param(value: str) -> str:
    """Wrap a value in Elisp-style quotes to match org-roam DB storage.

    Org-roam stores strings with embedded double quotes,
    e.g. the ID ``abc-123`` is stored as ``'"abc-123"'``.
    This wraps clean user input to match.
    """
    if value.startswith('"') and value.endswith('"'):
        return value
    return f'"{value}"'


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a read-only query and return results as list of dicts."""
    conn = get_connection()
    try:
        cursor = conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return [
            {col: _strip_elisp_quotes(val) for col, val in zip(columns, row)}
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()
