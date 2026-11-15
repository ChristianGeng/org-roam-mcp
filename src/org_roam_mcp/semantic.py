"""org_roam_search_similar: search the notes by meaning, with a local embedding model.

Needs the extra `semantic` (sentence-transformers). The notes are split into
pieces the way org_roam_search_text sees them: one or more per node (file
node or heading node with an ID), property drawers left out. Each piece is
embedded once; the vectors are kept in a SQLite file under the user's cache
folder, keyed by file, file hash and model, so only new and changed files are
embedded again. Nothing is sent anywhere; the model is downloaded once from
Hugging Face.
"""

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import sqlite3
from typing import Protocol
import unicodedata

import numpy as np

from . import db
from .search_text import SNIPPET_LENGTH
from .search_text import node_lines


DEFAULT_MODEL = "intfloat/multilingual-e5-small"
MODEL_ENV = "ORG_ROAM_MCP_EMBED_MODEL"
CACHE_ENV = "ORG_ROAM_MCP_CACHE_DIR"
CACHE_FILE = "semantic.sqlite"
# A node longer than this is split into pieces of equal size, so each piece
# has MAX_WORDS / 2 to MAX_WORDS words. e5-small reads at most 512 tokens,
# about 300-400 words; the rest of a longer piece would be cut off.
MAX_WORDS = 400
# Part of every file's hash: a change in how pieces are made embeds all
# files again.
PIECES_VERSION = "1"
BATCH_SIZE = 32


def available() -> bool:
    """Return whether sentence-transformers is installed (without importing it, which is slow)."""
    try:
        return importlib.util.find_spec("sentence_transformers") is not None
    except (ImportError, ValueError):
        return False


class Embedder(Protocol):
    """Turns texts into vectors of length 1 (one row per text)."""

    model: str
    query_prefix: str
    passage_prefix: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    """A sentence-transformers model, loaded once on first use."""

    def __init__(self, model: str):
        self.model = model
        # The e5 models were trained with these prefixes and are worse without.
        e5 = "e5" in model.lower()
        self.query_prefix = "query: " if e5 else ""
        self.passage_prefix = "passage: " if e5 else ""
        self._model = None

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model, device="cpu")
        vectors = self._model.encode(
            texts, batch_size=BATCH_SIZE, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)


_embedders: dict[str, SentenceTransformerEmbedder] = {}


def get_embedder() -> Embedder:
    """Return the embedder for ORG_ROAM_MCP_EMBED_MODEL (default DEFAULT_MODEL), kept between calls."""
    model = os.environ.get(MODEL_ENV) or DEFAULT_MODEL
    if model not in _embedders:
        _embedders[model] = SentenceTransformerEmbedder(model)
    return _embedders[model]


def cache_dir() -> Path:
    """Return ORG_ROAM_MCP_CACHE_DIR, else $XDG_CACHE_HOME/org-roam-mcp (default ~/.cache/org-roam-mcp)."""
    value = os.environ.get(CACHE_ENV)
    if value:
        return Path(value).expanduser()
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".cache") / "org-roam-mcp"


@dataclass
class Piece:
    node_id: str
    line: int
    text: str  # Without the title and tags in front; the snippet comes from it.


def node_pieces(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Split one node's lines into pieces of at most MAX_WORDS words, as (line of the first word, text).

    Whitespace is collapsed. A node without words gives no piece.
    """
    words = [(number, word) for number, line in lines for word in line.split()]
    if not words:
        return []
    count = math.ceil(len(words) / MAX_WORDS)
    size = math.ceil(len(words) / count)
    return [
        (words[start][0], " ".join(word for _, word in words[start : start + size]))
        for start in range(0, len(words), size)
    ]


def file_pieces(text: str, nodes: list[dict]) -> list[Piece]:
    """Return the pieces of one file; nodes are its rows from the nodes table (id, level)."""
    file_node = next((node["id"] for node in nodes if node["level"] == 0), None)
    pieces = []
    for node_id, lines in node_lines(text, {node["id"] for node in nodes}, file_node).items():
        pieces += [Piece(node_id, line, part) for line, part in node_pieces(lines)]
    return pieces


def passage(title: str, tags: list[str], text: str) -> str:
    """Return the text that is embedded for a piece: title and tags, then the piece."""
    head = title + (f" ({', '.join(tags)})" if tags else "")
    return f"{head}\n{text}" if head else text


def snippet(text: str) -> str:
    """Return the start of a piece, about SNIPPET_LENGTH characters."""
    return text if len(text) <= SNIPPET_LENGTH else text[:SNIPPET_LENGTH].rstrip() + "…"


class Cache:
    """The SQLite file with the pieces and their vectors."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                file TEXT, model TEXT, hash TEXT, PRIMARY KEY (file, model));
            CREATE TABLE IF NOT EXISTS pieces (
                file TEXT, model TEXT, node_id TEXT, line INTEGER, text TEXT, vec BLOB);
            CREATE INDEX IF NOT EXISTS pieces_file ON pieces (file, model);
            """
        )

    def close(self) -> None:
        self.conn.close()

    def hashes(self, model: str) -> dict[str, str]:
        return dict(self.conn.execute("SELECT file, hash FROM files WHERE model = ?", (model,)))

    def put(self, file: str, model: str, hash_: str, pieces: list[Piece], vectors: np.ndarray) -> None:
        with self.conn:
            self._delete(file, model)
            self.conn.execute("INSERT INTO files VALUES (?, ?, ?)", (file, model, hash_))
            self.conn.executemany(
                "INSERT INTO pieces VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (file, model, piece.node_id, piece.line, piece.text, vector.astype(np.float32).tobytes())
                    for piece, vector in zip(pieces, vectors)
                ],
            )

    def _delete(self, file: str, model: str | None = None) -> None:
        where, params = ("file = ?", (file,)) if model is None else ("file = ? AND model = ?", (file, model))
        self.conn.execute(f"DELETE FROM files WHERE {where}", params)
        self.conn.execute(f"DELETE FROM pieces WHERE {where}", params)

    def drop_except(self, files: set[str]) -> int:
        """Delete the entries (of every model) of files that are not in files; return how many files."""
        gone = {row[0] for row in self.conn.execute("SELECT DISTINCT file FROM files")} - files
        with self.conn:
            for file in gone:
                self._delete(file)
        return len(gone)

    def pieces(self, model: str, files: set[str]) -> tuple[list[tuple[str, str, int, str]], np.ndarray]:
        """Return the pieces of files as (file, node id, line, text), and their vectors as one matrix."""
        rows = [
            row
            for row in self.conn.execute(
                "SELECT file, node_id, line, text, vec FROM pieces WHERE model = ? ORDER BY rowid", (model,)
            )
            if row[0] in files
        ]
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32)
        vectors = np.stack([np.frombuffer(row[4], dtype=np.float32) for row in rows])
        return [row[:4] for row in rows], vectors


@dataclass
class IndexStats:
    files: int = 0  # Files in the database that could be read.
    embedded: int = 0  # Files embedded in this call (new or changed).
    pieces: int = 0  # Pieces embedded in this call.
    unreadable: int = 0
    dropped: int = 0  # Files in the cache that are no longer in the database.


def _roam_rows(tag: str | None) -> tuple[list[dict], list[dict], list[dict], set[str] | None]:
    """Read nodes, files and tags in one transaction; with tag, also the nodes that have it."""
    conn = db.get_connection()
    try:
        conn.execute("BEGIN")
        node_rows = db.query("SELECT id, title, file, level FROM nodes", conn=conn)
        file_rows = db.query("SELECT file FROM files", conn=conn)
        has_tags = db.query("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'tags'", conn=conn)
        tag_rows = db.query("SELECT node_id, tag FROM tags", conn=conn) if has_tags else []
    finally:
        conn.close()
    allowed = {row["node_id"] for row in tag_rows if row["tag"] == tag} if tag else None
    return node_rows, file_rows, tag_rows, allowed


def index(
    embedder: Embedder, tag: str | None = None, progress: Callable[[str], None] | None = None
) -> tuple[Cache, IndexStats, dict[str, dict], set[str] | None, set[str]]:
    """Bring the cache up to date with the files of the database and return it.

    Returns the open cache, the counts, the nodes by ID, the IDs allowed by
    tag (None without tag), and the files that are indexed.
    """
    node_rows, file_rows, tag_rows, allowed = _roam_rows(tag)
    nodes_by_file: dict[str, list[dict]] = {}
    for row in node_rows:
        nodes_by_file.setdefault(row["file"], []).append(row)
    tags: dict[str, list[str]] = {}
    for row in tag_rows:
        tags.setdefault(row["node_id"], []).append(row["tag"])

    stats = IndexStats()
    cache = Cache(cache_dir() / CACHE_FILE)
    try:
        known = cache.hashes(embedder.model)
        present = {row["file"] for row in file_rows}
        stats.dropped = cache.drop_except(present)
        indexed = set()
        for file in sorted(present):
            nodes = nodes_by_file.get(file, [])
            try:
                raw = Path(file).read_bytes()
                text = unicodedata.normalize("NFC", raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n"))
            except (OSError, UnicodeDecodeError):
                stats.unreadable += 1
                continue
            stats.files += 1
            indexed.add(file)
            # The titles and tags come from the database, so they are part of the hash.
            meta = sorted((n["id"], n["level"], n["title"] or "", sorted(tags.get(n["id"], []))) for n in nodes)
            hash_ = hashlib.sha1(PIECES_VERSION.encode() + b"\0" + raw + b"\0" + repr(meta).encode()).hexdigest()
            if known.get(file) == hash_:
                continue
            pieces = file_pieces(text, nodes)
            by_id = {node["id"]: node for node in nodes}
            texts = [
                embedder.passage_prefix + passage(by_id[p.node_id]["title"] or "", tags.get(p.node_id, []), p.text)
                for p in pieces
            ]
            vectors = embedder.encode(texts) if texts else np.zeros((0, 0), dtype=np.float32)
            cache.put(file, embedder.model, hash_, pieces, vectors)
            stats.embedded += 1
            stats.pieces += len(pieces)
            if progress:
                progress(f"embedded {file} ({len(pieces)} pieces)")
    except BaseException:
        cache.close()
        raise
    by_id = {row["id"]: row for row in node_rows}
    return cache, stats, by_id, allowed, indexed


@dataclass
class Hit:
    node_id: str
    title: str
    file: str
    line: int
    snippet: str
    score: float


def similar(
    query: str, limit: int = 10, tag: str | None = None, embedder: Embedder | None = None
) -> tuple[list[Hit], IndexStats]:
    """Return the nodes most similar to query, best first, one per node (its best piece).

    A limit below 1 returns nothing, without indexing.
    """
    if limit < 1:
        return [], IndexStats()
    embedder = embedder or get_embedder()
    cache, stats, by_id, allowed, indexed = index(embedder, tag)
    try:
        rows, vectors = cache.pieces(embedder.model, indexed)
    finally:
        cache.close()
    if not rows:
        return [], stats
    query_vector = embedder.encode([embedder.query_prefix + query])[0]
    scores = vectors @ query_vector
    best: dict[str, Hit] = {}
    for i in np.argsort(-scores, kind="stable"):
        file, node_id, line, text = rows[i]
        if node_id in best or node_id not in by_id or (allowed is not None and node_id not in allowed):
            continue
        best[node_id] = Hit(node_id, by_id[node_id]["title"] or "", file, line, snippet(text), float(scores[i]))
        if len(best) == limit:
            break
    return list(best.values()), stats


def search_similar(query: str, limit: int = 10, tag: str | None = None, embedder: Embedder | None = None) -> str:
    """Search the notes by meaning; see org_roam_search_similar."""
    if not query.strip():
        return "Error: query is empty."
    if limit < 1:
        return "Error: limit must be at least 1."
    hits, stats = similar(query, limit, tag, embedder)
    if hits:
        out = [f'Notes similar to "{query}" ({len(hits)}):']
        out += [f"{hit.node_id} | {hit.title} | {hit.file}:{hit.line} | {hit.snippet}" for hit in hits]
    else:
        out = [f"No notes to compare with: {query}"]
    if stats.unreadable:
        n = stats.unreadable
        out.append(f"{n} file{'' if n == 1 else 's'} could not be read (not UTF-8, or missing).")
    return "\n".join(out)
