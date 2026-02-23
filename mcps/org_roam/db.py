"""SQLite connection and org-roam database detection."""

import os
import sqlite3
import subprocess
from pathlib import Path


def detect_db() -> str:
    """Locate the org-roam SQLite database.

    Detection order:
    1. ORG_ROAM_DB environment variable
    2. emacsclient --eval org-roam-db-location
    3. Common filesystem locations
    """
    env_db = os.environ.get("ORG_ROAM_DB")
    if env_db and Path(env_db).is_file():
        return env_db

    try:
        result = subprocess.run(
            ["emacsclient", "--eval", "org-roam-db-location"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            path = result.stdout.strip().strip('"')
            if Path(path).is_file():
                return path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

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
        if loc.is_file():
            return str(loc)

    raise FileNotFoundError(
        "org-roam.db not found. Set ORG_ROAM_DB environment variable."
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
