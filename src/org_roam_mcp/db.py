"""SQLite connection and org-roam database detection."""

import os
from pathlib import Path
import sqlite3
import subprocess
import time


REQUIRED_TABLES = {"files", "nodes"}
# How long a found database is used without looking again. Each query asks
# for the database; without this, an Emacs that does not answer would cost
# up to five seconds per server on every query.
CACHE_SECONDS = 60.0
_cached: tuple[float, str] | None = None
# The path is the expression's value, which emacsclient prints. `princ'
# would write into the server's current buffer, and fails when that buffer
# is read-only (for example *Process List*).
EMACS_DB_LOCATION_EVAL = (
    "(progn "
    "(require 'org-roam nil t) "
    "(let ((loc (cond "
    "((fboundp 'org-roam-db-location) (org-roam-db-location)) "
    "((boundp 'org-roam-db-location) org-roam-db-location) "
    "(t nil)))) "
    "(when loc (expand-file-name loc))))"
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
    """Return likely Emacs server socket locations for the current user.

    These are the sockets of the default server name. A TCP server is reached
    by the plain emacsclient call when EMACS_SERVER_FILE is set, because
    emacsclient reads that variable itself. A server with another name is
    asked with --socket-name when EMACS_SOCKET_NAME is set (see
    _server_targets), because emacsclient reads that variable itself only
    from Emacs 27 on.
    """
    uid = os.getuid()
    return [
        f"/run/user/{uid}/emacs/server",
        f"/tmp/emacs{uid}/server",
    ]


def _xdg_config_home() -> Path:
    """Return $XDG_CONFIG_HOME, or ~/.config when it is unset or empty."""
    value = os.environ.get("XDG_CONFIG_HOME")
    if value:
        return Path(value).expanduser()
    return Path.home() / ".config"


def fallback_locations() -> list[Path]:
    """Return the standard places of org-roam.db, in the order they are tried.

    Vanilla Emacs keeps the database in the Emacs folder, Doom in its cache
    folder; both Emacs folders are tried: ~/.emacs.d and
    $XDG_CONFIG_HOME/emacs (default ~/.config/emacs).
    """
    places = []
    for emacs_dir in (Path.home() / ".emacs.d", _xdg_config_home() / "emacs"):
        places.append(emacs_dir / "org-roam.db")
        places.append(emacs_dir / ".local" / "cache" / "org-roam.db")
    return places


def _server_targets() -> list[tuple[str | None, str | None]]:
    """Return the Emacs servers to ask, as (server_file, socket_name), in order.

    First the default server, then the one named by EMACS_SOCKET_NAME (passed
    explicitly, so it also works with Emacs 26), then the default sockets.
    """
    targets: list[tuple[str | None, str | None]] = [(None, None)]
    socket_name = os.environ.get("EMACS_SOCKET_NAME")
    if socket_name:
        targets.append((None, socket_name))
    targets.extend((server_file, None) for server_file in _server_file_candidates())
    return targets


def _detect_db_from_server(server_file: str | None = None, socket_name: str | None = None) -> str | None:
    """Try to detect org-roam DB path via emacsclient against a server."""
    command = ["emacsclient"]
    if server_file:
        command.extend(["--server-file", server_file])
    if socket_name:
        command.extend(["--socket-name", socket_name])
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


def _server_label(server_file: str | None, socket_name: str | None = None) -> str:
    """Describe one Emacs server attempt for the error message."""
    if socket_name:
        return f"Emacs server named by EMACS_SOCKET_NAME={socket_name} (emacsclient --socket-name)"
    if server_file is None:
        return "Emacs server through emacsclient (default name, or EMACS_SERVER_FILE if set)"
    return f"Emacs server at {server_file}"


def detect_db() -> str:
    """Return the org-roam database, found by _find_db and kept for CACHE_SECONDS.

    A kept path is used only while it is still an org-roam database; after
    CACHE_SECONDS, or when the file is gone, the lookup runs again.
    """
    global _cached
    if _cached is not None:
        found_at, path = _cached
        if time.monotonic() - found_at < CACHE_SECONDS and _is_valid_roam_db(Path(path)):
            return path
    path = _find_db()
    _cached = (time.monotonic(), path)
    return path


def _find_db() -> str:
    """Locate the org-roam SQLite database.

    Detection order:
    1. A running Emacs, asked through emacsclient for org-roam-db-location
    2. The ORG_ROAM_DB environment variable
    3. The standard places (see fallback_locations)

    Raises FileNotFoundError with every place tried when none holds a
    usable org-roam database.
    """
    tried = []
    for server_file, socket_name in _server_targets():
        server_db = _detect_db_from_server(server_file, socket_name)
        if server_db:
            return server_db
        tried.append(_server_label(server_file, socket_name))

    env_db = os.environ.get("ORG_ROAM_DB")
    if env_db:
        env_path = Path(env_db).expanduser()
        if _is_valid_roam_db(env_path):
            return str(env_path)
        tried.append(f"ORG_ROAM_DB={env_path} (not an org-roam database)")
    else:
        tried.append("ORG_ROAM_DB (not set)")

    for loc in fallback_locations():
        if _is_valid_roam_db(loc):
            return str(loc)
        tried.append(str(loc))

    lines = "\n".join(f"  {i}. {place}" for i, place in enumerate(tried, 1))
    raise FileNotFoundError(
        "org-roam.db not found. Places tried, in this order:\n"
        f"{lines}\n"
        "To fix it, either set ORG_ROAM_DB to the full path of your org-roam.db, "
        "or start Emacs with org-roam loaded and run (server-start)."
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
        return [{col: _strip_elisp_quotes(val) for col, val in zip(columns, row)} for row in cursor.fetchall()]
    finally:
        conn.close()
