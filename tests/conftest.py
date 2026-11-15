"""Shared fixtures: synthetic notes and an org-roam database that knows them."""

import sqlite3

import pytest

import org_roam_mcp.db as db_module


GARDEN = """:PROPERTIES:
:ID: file-garden
:END:
#+title: Garden

The tomatoes grow next to the basil.
Water the tomatoes in the morning.

* Compost
:PROPERTIES:
:ID: head-compost
:END:
The compost heap needs brown leaves and green cuttings.

* Plain heading
Seeds of the pumpkin are dried in autumn.
"""

KITCHEN = """:PROPERTIES:
:ID: file-kitchen
:END:
#+title: Kitchen

A sauce of tomatoes and basil, cooked slowly.
More basil, and basil on top.
"""

TRAVEL = """:PROPERTIES:
:ID: file-travel
:ROAM_ALIASES: secretword
:END:
#+title: Travel

A green train goes through the hills.
"""


@pytest.fixture
def notes(tmp_path, monkeypatch):
    """Write three synthetic notes and an org-roam database that knows them."""
    files = {}
    for name, text in [("garden.org", GARDEN), ("kitchen.org", KITCHEN), ("travel.org", TRAVEL)]:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        files[name] = str(path)
    db_path = tmp_path / "org-roam.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE files (file TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, file TEXT, level INTEGER, pos INTEGER, title TEXT)")
    conn.execute("CREATE TABLE tags (node_id TEXT, tag TEXT)")
    nodes = [
        ("file-garden", "garden.org", 0, 1, "Garden"),
        ("head-compost", "garden.org", 1, 120, "Compost"),
        ("file-kitchen", "kitchen.org", 0, 1, "Kitchen"),
        ("file-travel", "travel.org", 0, 1, "Travel"),
    ]
    for node_id, name, level, pos, title in nodes:
        conn.execute(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?)", (f'"{node_id}"', f'"{files[name]}"', level, pos, f'"{title}"')
        )
    for path in files.values():
        conn.execute("INSERT INTO files VALUES (?)", (f'"{path}"',))
    conn.execute("INSERT INTO tags VALUES (?, ?)", ('"file-kitchen"', '"food"'))
    conn.commit()
    conn.close()
    monkeypatch.setattr(db_module, "detect_db", lambda: str(db_path))
    return {"dir": tmp_path, "db": db_path, **files}
