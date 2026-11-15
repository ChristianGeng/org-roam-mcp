"""Tests for org_roam_search_similar, with a fake embedder (no model, no network) and synthetic notes."""

import asyncio
import importlib.util
from pathlib import Path
import re
import sqlite3
import sys
import zlib

from mcp.server.fastmcp import FastMCP
import numpy as np
import pytest

from org_roam_mcp import semantic
from org_roam_mcp import tools_roam


SCRIPT = Path(__file__).parent.parent / "scripts" / "compare_search.py"


class FakeEmbedder:
    """Bag of words hashed into 256 dimensions, normalized; remembers every text it embeds."""

    query_prefix = "query: "
    passage_prefix = "passage: "

    def __init__(self, model: str = "fake-model"):
        self.model = model
        self.texts: list[str] = []

    def encode(self, texts: list[str]) -> np.ndarray:
        self.texts += texts
        vectors = np.zeros((len(texts), 256), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"\w+", text.lower()):
                if word not in ("query", "passage", "the", "a", "and", "of", "in"):
                    vectors[row, zlib.crc32(word.encode()) % 256] += 1
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)

    def passages(self) -> list[str]:
        return [text for text in self.texts if text.startswith(self.passage_prefix)]


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    """Keep the vectors in a temporary folder."""
    monkeypatch.setenv(semantic.CACHE_ENV, str(tmp_path / "cache"))
    return tmp_path / "cache" / semantic.CACHE_FILE


def _rows(result: str) -> list[list[str]]:
    """Return the result lines after the heading, split into their four columns."""
    return [line.split(" | ") for line in result.splitlines()[1:] if " | " in line]


class TestPieces:
    def test_short_node_is_one_piece_from_its_first_line(self):
        """Whitespace is collapsed; the line is the one of the first word."""
        assert semantic.node_pieces([(3, ""), (4, "  one  two"), (5, "three")]) == [(4, "one two three")]

    def test_node_without_words_has_no_piece(self):
        """Blank lines give no piece."""
        assert semantic.node_pieces([(1, ""), (2, "   ")]) == []

    def test_long_node_is_split_into_equal_pieces(self):
        """900 words become three pieces of 300, each with the line of its first word."""
        lines = [(10 + i, " ".join(f"w{i}x{j}" for j in range(10))) for i in range(90)]
        pieces = semantic.node_pieces(lines)
        assert [len(text.split()) for _, text in pieces] == [300, 300, 300]
        assert [line for line, _ in pieces] == [10, 40, 70]

    def test_pieces_follow_the_nodes_of_the_text_search(self, notes):
        """A heading with an ID is its own node; one without belongs to the file; drawers are left out."""
        text = Path(notes["garden.org"]).read_text(encoding="utf-8")
        nodes = [{"id": "file-garden", "level": 0}, {"id": "head-compost", "level": 1}]
        pieces = {piece.node_id: piece for piece in semantic.file_pieces(text, nodes)}
        assert set(pieces) == {"file-garden", "head-compost"}
        assert pieces["head-compost"].line == 9
        assert pieces["head-compost"].text.startswith("* Compost The compost heap")
        assert "pumpkin" in pieces["file-garden"].text
        assert ":ID:" not in pieces["file-garden"].text and "PROPERTIES" not in pieces["file-garden"].text

    def test_title_tags_and_prefixes_go_in_front(self, notes):
        """Passages get "passage: ", title and tags; the query gets "query: "."""
        fake = FakeEmbedder()
        semantic.search_similar("sauce", embedder=fake)
        kitchen = [text for text in fake.passages() if "sauce" in text]
        assert kitchen == [
            "passage: Kitchen (food)\n#+title: Kitchen A sauce of tomatoes and basil, cooked slowly. "
            "More basil, and basil on top."
        ]
        assert any(text.startswith("passage: Compost\n* Compost") for text in fake.passages())
        assert fake.texts[-1] == "query: sauce"

    def test_e5_models_get_prefixes_and_others_none(self, monkeypatch):
        """The real embedder sets the prefixes by model name, and imports nothing until it encodes."""
        monkeypatch.setitem(sys.modules, "sentence_transformers", None)
        e5 = semantic.SentenceTransformerEmbedder("intfloat/multilingual-e5-small")
        assert (e5.query_prefix, e5.passage_prefix) == ("query: ", "passage: ")
        other = semantic.SentenceTransformerEmbedder("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        assert (other.query_prefix, other.passage_prefix) == ("", "")

    def test_model_from_the_environment(self, monkeypatch):
        """ORG_ROAM_MCP_EMBED_MODEL picks the model; the default is multilingual-e5-small."""
        monkeypatch.delenv(semantic.MODEL_ENV, raising=False)
        assert semantic.get_embedder().model == "intfloat/multilingual-e5-small"
        monkeypatch.setenv(semantic.MODEL_ENV, "some/other-model")
        assert semantic.get_embedder().model == "some/other-model"


class TestSearchSimilar:
    def test_most_similar_first_with_the_best_piece(self, notes):
        """The node about compost comes first, with its file, line and the start of its piece."""
        result = semantic.search_similar("brown leaves for the compost heap", embedder=FakeEmbedder())
        assert result.splitlines()[0].startswith('Notes similar to "brown leaves for the compost heap" (')
        rows = _rows(result)
        assert rows[0][:3] == ["head-compost", "Compost", f"{notes['garden.org']}:9"]
        assert rows[0][3].startswith("* Compost The compost heap")
        assert [row[0] for row in rows].count("head-compost") == 1

    def test_ordering(self, notes):
        """Kitchen (sauce, basil three times) before Garden for a question about basil sauce."""
        rows = _rows(semantic.search_similar("basil sauce", embedder=FakeEmbedder()))
        assert [row[0] for row in rows][:2] == ["file-kitchen", "file-garden"]
        assert {row[0] for row in rows} == {"file-kitchen", "file-garden", "head-compost", "file-travel"}

    def test_one_line_per_node(self, notes):
        """A node with several pieces is listed once, with its best piece."""
        with open(notes["travel.org"], "a", encoding="utf-8") as f:
            f.write("filler " * 500 + "\nThe train stops at the old harbour.\n")
        fake = FakeEmbedder()
        rows = _rows(semantic.search_similar("train harbour", embedder=fake))
        assert len([text for text in fake.passages() if text.startswith("passage: Travel\n")]) == 2
        assert [row[0] for row in rows].count("file-travel") == 1
        assert rows[0][0] == "file-travel"

    def test_limit(self, notes):
        """At most limit nodes; a limit below 1 is an error."""
        result = semantic.search_similar("tomatoes", limit=1, embedder=FakeEmbedder())
        assert result.splitlines()[0] == 'Notes similar to "tomatoes" (1):'
        assert len(_rows(result)) == 1
        assert semantic.search_similar("tomatoes", limit=0, embedder=FakeEmbedder()) == (
            "Error: limit must be at least 1."
        )

    def test_tag(self, notes):
        """Only nodes with the tag."""
        rows = _rows(semantic.search_similar("compost", tag="food", embedder=FakeEmbedder()))
        assert [row[0] for row in rows] == ["file-kitchen"]
        assert semantic.search_similar("compost", tag="nosuchtag", embedder=FakeEmbedder()) == (
            "No notes to compare with: compost"
        )

    def test_empty_query(self, notes):
        """A query without words is an error, and nothing is embedded."""
        fake = FakeEmbedder()
        assert semantic.search_similar("   ", embedder=fake) == "Error: query is empty."
        assert fake.texts == []

    def test_unreadable_file_is_counted(self, notes):
        """A file that is not UTF-8 is skipped and counted, not an error."""
        with open(notes["kitchen.org"], "wb") as f:
            f.write(b"#+title: Kitchen\n\xff\xfe tomatoes\n")
        result = semantic.search_similar("tomatoes", embedder=FakeEmbedder())
        assert "file-kitchen" not in result
        assert result.splitlines()[-1] == "1 file could not be read (not UTF-8, or missing)."


class TestCache:
    def test_unchanged_files_are_not_embedded_again(self, notes, cache):
        """The second search embeds only the query."""
        fake = FakeEmbedder()
        first = semantic.search_similar("tomatoes", embedder=fake)
        assert len(fake.passages()) == 4
        assert cache.is_file()
        fake.texts.clear()
        assert semantic.search_similar("tomatoes", embedder=fake) == first
        assert fake.texts == ["query: tomatoes"]

    def test_a_changed_file_is_embedded_again(self, notes):
        """Only the changed file's pieces are embedded, and the new text is found."""
        fake = FakeEmbedder()
        semantic.search_similar("tomatoes", embedder=fake)
        with open(notes["kitchen.org"], "a", encoding="utf-8") as f:
            f.write("Bake the bread with rosemary.\n")
        fake.texts.clear()
        rows = _rows(semantic.search_similar("rosemary bread", embedder=fake))
        assert [text.split("\n")[0] for text in fake.passages()] == ["passage: Kitchen (food)"]
        assert rows[0][0] == "file-kitchen"

    def test_a_changed_tag_embeds_the_file_again(self, notes):
        """Tags are in front of each piece, so a new tag in the database embeds that file again."""
        fake = FakeEmbedder()
        semantic.search_similar("tomatoes", embedder=fake)
        conn = sqlite3.connect(notes["db"])
        conn.execute("INSERT INTO tags VALUES (?, ?)", ('"file-travel"', '"trips"'))
        conn.commit()
        conn.close()
        fake.texts.clear()
        semantic.search_similar("tomatoes", embedder=fake)
        assert fake.passages() == ["passage: Travel (trips)\n#+title: Travel A green train goes through the hills."]

    def test_another_model_has_its_own_vectors(self, notes):
        """Changing the model embeds everything again; the first model's vectors stay."""
        semantic.search_similar("tomatoes", embedder=FakeEmbedder("model-a"))
        other = FakeEmbedder("model-b")
        semantic.search_similar("tomatoes", embedder=other)
        assert len(other.passages()) == 4
        again = FakeEmbedder("model-a")
        semantic.search_similar("tomatoes", embedder=again)
        assert again.passages() == []

    def test_files_no_longer_in_the_database_are_dropped(self, notes, cache):
        """A file removed from the database is removed from the cache and not found."""
        semantic.search_similar("tomatoes", embedder=FakeEmbedder())
        conn = sqlite3.connect(notes["db"])
        conn.execute("DELETE FROM files WHERE file = ?", (f'"{notes["kitchen.org"]}"',))
        conn.commit()
        conn.close()
        rows = _rows(semantic.search_similar("basil sauce", embedder=FakeEmbedder()))
        assert "file-kitchen" not in [row[0] for row in rows]
        conn = sqlite3.connect(cache)
        files = {row[0] for row in conn.execute("SELECT file FROM files")}
        pieces = {row[0] for row in conn.execute("SELECT file FROM pieces")}
        conn.close()
        assert notes["kitchen.org"] not in files | pieces
        assert notes["garden.org"] in files

    def test_cache_folder(self, monkeypatch, tmp_path):
        """ORG_ROAM_MCP_CACHE_DIR, else $XDG_CACHE_HOME/org-roam-mcp, else ~/.cache/org-roam-mcp."""
        monkeypatch.setenv(semantic.CACHE_ENV, str(tmp_path / "here"))
        assert semantic.cache_dir() == tmp_path / "here"
        monkeypatch.delenv(semantic.CACHE_ENV)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
        assert semantic.cache_dir() == tmp_path / "xdg" / "org-roam-mcp"
        monkeypatch.delenv("XDG_CACHE_HOME")
        assert semantic.cache_dir() == Path.home() / ".cache" / "org-roam-mcp"


class TestRegistration:
    def _tools(self) -> dict:
        mcp = FastMCP("test")
        tools_roam.register(mcp)
        return {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    def test_not_registered_without_the_extra(self, monkeypatch):
        """When sentence_transformers cannot be imported, the tool is not there; the others are."""
        monkeypatch.setitem(sys.modules, "sentence_transformers", None)
        assert not semantic.available()
        tools = self._tools()
        assert "org_roam_search_similar" not in tools
        assert "org_roam_search_text" in tools

    def test_registered_with_the_extra(self, monkeypatch):
        """With the extra, the tool takes query, limit and tag."""
        monkeypatch.setattr(semantic, "available", lambda: True)
        params = self._tools()["org_roam_search_similar"].inputSchema["properties"]
        assert set(params) == {"query", "limit", "tag"}


class TestCompareScript:
    @pytest.fixture
    def script(self, monkeypatch):
        """Load scripts/compare_search.py with the fake embedder."""
        spec = importlib.util.spec_from_file_location("compare_search", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(semantic, "get_embedder", lambda: FakeEmbedder())
        return module

    def test_side_by_side_with_recall_and_times(self, notes, script, capsys, tmp_path):
        """Both top lists, expected IDs marked, recall@10 per question and on average, and the times."""
        questions = tmp_path / "questions.txt"
        questions.write_text(
            "# question | expected IDs\n\nbasil sauce | file-kitchen, file-travel\nwhere is the compost heap\n",
            encoding="utf-8",
        )
        assert script.main([str(questions)]) == 0
        out = capsys.readouterr().out
        assert "Model: fake-model" in out
        assert re.search(r"Model loaded: [\d.]+ s", out)
        assert re.search(r"Index: [\d.]+ s; 3 files, 3 embedded now \(4 pieces\)", out)
        assert "1. basil sauce" in out and "2. where is the compost heap" in out
        first = out.split("1. basil sauce")[1].split("2. where")[0]
        assert re.search(r"1  \*Kitchen \(file-kitchen\)\s+\*Kitchen \(file-kitchen\)", first)
        assert "recall@10: text 0.50, by meaning 1.00" in first
        second = out.split("2. where is the compost heap")[1]
        assert "(nothing)" in second and "recall" not in second.split("Summary")[0]
        assert re.search(r"text search: mean time [\d.]+ s, mean recall@10 0.50 \(1 questions with IDs\)", out)
        assert re.search(r"by meaning: mean time [\d.]+ s, mean recall@10 1.00", out)

    def test_read_questions(self, script, tmp_path):
        """IDs after | are split at spaces and commas; comments and blank lines are skipped."""
        path = tmp_path / "q.txt"
        path.write_text("# c\n\nWann blüht der Kürbis? | a, b  c\nno ids\n", encoding="utf-8")
        assert [(q.text, q.expected) for q in script.read_questions(str(path))] == [
            ("Wann blüht der Kürbis?", ["a", "b", "c"]),
            ("no ids", []),
        ]
