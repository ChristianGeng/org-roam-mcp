"""Tests for org_roam_search_text, with synthetic notes in a temporary directory."""

import asyncio
import sqlite3

import pytest

import org_roam_mcp.db as db_module
from org_roam_mcp.search_text import parse_query
from org_roam_mcp.search_text import search_lines
from org_roam_mcp.search_text import search_text


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


def _rows(result: str) -> list[list[str]]:
    """Return the result lines after the heading, split into their four columns."""
    return [line.split(" | ") for line in result.splitlines()[1:] if " | " in line]


class TestSearchText:
    def test_word_in_the_body_of_a_file_node(self, notes):
        """A word in the body is found in the file's node, with line and marked snippet."""
        rows = _rows(search_text("morning"))
        assert len(rows) == 1
        node_id, title, place, snippet = rows[0]
        assert (node_id, title) == ("file-garden", "Garden")
        assert place == f"{notes['garden.org']}:7"
        assert "**morning**" in snippet

    def test_word_under_a_heading_that_is_its_own_node(self, notes):
        """A word under a heading node belongs to that node, not to the file's node."""
        rows = _rows(search_text("HEAP"))
        assert [row[0] for row in rows] == ["head-compost"]
        assert rows[0][2].endswith("garden.org:13")

    def test_word_under_a_heading_without_an_id_belongs_to_the_file(self, notes):
        """A heading without an ID is part of the file's node."""
        rows = _rows(search_text("pumpkin"))
        assert [row[0] for row in rows] == ["file-garden"]
        assert rows[0][2].endswith("garden.org:16")

    def test_several_words_must_all_occur_in_any_order(self, notes):
        """All words must be in the node; their order does not matter."""
        rows = _rows(search_text("basil tomatoes"))
        assert {row[0] for row in rows} == {"file-garden", "file-kitchen"}
        assert _rows(search_text("basil compost")) == []

    def test_more_hits_first_then_title(self, notes):
        """Kitchen has basil three times, Garden once; "green" is once in each."""
        assert [row[1] for row in _rows(search_text("basil"))] == ["Kitchen", "Garden"]
        assert [row[1] for row in _rows(search_text("tomatoes"))] == ["Garden", "Kitchen"]
        assert [row[1] for row in _rows(search_text("green"))] == ["Compost", "Travel"]

    def test_limit(self, notes):
        """At most limit nodes are returned."""
        result = search_text("tomatoes", limit=1)
        assert result.splitlines()[0] == 'Notes containing "tomatoes" (1):'
        assert [row[1] for row in _rows(result)] == ["Garden"]

    def test_quoted_phrase(self, notes):
        """A phrase in double quotes is found only as a whole."""
        rows = _rows(search_text('"tomatoes and basil"'))
        assert [row[0] for row in rows] == ["file-kitchen"]
        assert "**tomatoes and basil**" in rows[0][3]
        assert _rows(search_text('"basil and tomatoes"')) == []

    def test_limit_below_one(self, notes):
        """A limit below 1 is an error, not "no notes"."""
        assert search_text("tomatoes", limit=0) == "Error: limit must be at least 1."

    def test_drawer_syntax_in_a_block_is_text(self, notes):
        """Inside #+begin_example, :PROPERTIES: and :ID: are text, not a drawer."""
        with open(notes["travel.org"], "a", encoding="utf-8") as f:
            f.write("#+begin_example\n:PROPERTIES:\n:ID: not-a-node\n#+end_example\nThe blue lake.\n")
        assert [row[0] for row in _rows(search_text("lake"))] == ["file-travel"]
        assert [row[0] for row in _rows(search_text("not-a-node"))] == ["file-travel"]

    def test_phrase_does_not_go_over_a_child_node(self, notes):
        """The Compost section is between "morning." and "* Plain heading" in the file node."""
        assert _rows(search_text('"morning. * plain heading"')) == []
        with open(notes["travel.org"], "a", encoding="utf-8") as f:
            f.write("The road ends\nat the sea.\n")
        assert [row[0] for row in _rows(search_text('"road ends at the sea"'))] == ["file-travel"]

    def test_case_folding_beyond_ascii(self, notes):
        """İ (which lower-cases to two characters) and final sigma match."""
        with open(notes["travel.org"], "a", encoding="utf-8") as f:
            f.write("From İzmir along the ΟΔΟΣ.\n")
        assert [row[0] for row in _rows(search_text("İZMIR"))] == ["file-travel"]
        assert [row[0] for row in _rows(search_text("οδος"))] == ["file-travel"]

    def test_no_hit(self, notes):
        """No node contains the word."""
        assert search_text("submarine") == "No notes contain: submarine"

    def test_empty_query(self, notes):
        """A query without words is an error."""
        assert search_text('  "" ') == "Error: query is empty."

    def test_property_drawers_and_ids_are_not_searched(self, notes):
        """Words and IDs in property drawers are not hits."""
        assert search_text("secretword") == "No notes contain: secretword"
        assert search_text("file-garden") == "No notes contain: file-garden"
        assert ":ID:" not in search_text("tomatoes")

    def test_tag_filter(self, notes):
        """Only nodes with the tag are returned."""
        rows = _rows(search_text("tomatoes", tag="food"))
        assert [row[0] for row in rows] == ["file-kitchen"]
        assert search_text("compost", tag="food") == "No notes contain: compost"

    def test_unreadable_file_is_counted(self, notes):
        """A file that is not UTF-8 is skipped and counted, not an error."""
        with open(notes["kitchen.org"], "wb") as f:
            f.write(b"#+title: Kitchen\n\xff\xfe tomatoes\n")
        result = search_text("tomatoes")
        assert [row[0] for row in _rows(result)] == ["file-garden"]
        assert result.splitlines()[-1] == "1 file could not be read (not UTF-8, or missing)."

    def test_long_line_gives_a_short_snippet(self, notes):
        """The snippet is about 120 characters around the hit, cut with an ellipsis."""
        with open(notes["travel.org"], "a", encoding="utf-8") as f:
            f.write("word " * 100 + "needle " + "word " * 100 + "\n")
        snippet = _rows(search_text("needle"))[0][3]
        assert snippet.startswith("…") and snippet.endswith("…")
        assert "**needle**" in snippet
        assert 115 <= len(snippet) <= 130


class TestSearchLines:
    def test_phrase_does_not_go_over_left_out_lines(self):
        """Lines 8 to 14 were left out (a drawer or a child node), so the phrase is not there."""
        assert search_lines([(7, "in the morning."), (15, "Seeds here.")], ["morning. seeds"]) is None
        hit = search_lines([(7, "in the morning."), (8, "Seeds here.")], ["morning. seeds"])
        assert hit == (1, 7, "in the **morning. Seeds** here.")


class TestParseQuery:
    def test_words_and_phrases(self):
        """Words are split at spaces; a quoted phrase stays one term."""
        assert parse_query('Basil "Green  Tomatoes" basil') == ["basil", "green tomatoes"]

    def test_unclosed_quote(self):
        """An unclosed quote is ignored."""
        assert parse_query('"tomatoes basil') == ["tomatoes", "basil"]


def test_the_server_has_the_tool():
    """The server registers org_roam_search_text with query, limit and tag."""
    from org_roam_mcp.server import mcp

    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    params = tools["org_roam_search_text"].inputSchema["properties"]
    assert set(params) == {"query", "limit", "tag"}
