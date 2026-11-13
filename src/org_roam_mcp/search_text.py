"""org_roam_search_text: search the text of the notes, not only their titles.

The files are the ones in the database's `files` table. Each call reads
them once; there is no index.
"""

from bisect import bisect_right
from pathlib import Path
import re
import unicodedata

from . import db


SNIPPET_LENGTH = 120
MARK = "**"
_TERM = re.compile(r'"([^"]*)"|(\S+)')
_HEADING = re.compile(r"^(\*+)\s")
_ID_LINE = re.compile(r"^\s*:ID:\s*(\S+)\s*$", re.IGNORECASE)
_DRAWER_START = re.compile(r"^\s*:PROPERTIES:\s*$", re.IGNORECASE)
_DRAWER_END = re.compile(r"^\s*:END:\s*$", re.IGNORECASE)
_BLOCK_START = re.compile(r"^\s*#\+begin_(\S+)", re.IGNORECASE)
_BLOCK_END = re.compile(r"^\s*#\+end_(\S+)", re.IGNORECASE)
# Joins lines that are not next to each other (a drawer or a child node was
# between them). No term contains it, so a phrase cannot match over the gap.
_GAP = "\n"


class _FoldTable(dict):
    """Map each character to its case-folded form (ß to ss), and remember it."""

    def __missing__(self, code: int) -> str:
        folded = chr(code).casefold()
        self[code] = folded
        return folded


_FOLD_TABLE = _FoldTable()


def parse_query(query: str) -> list[str]:
    """Split a query into lower-case terms: words, and phrases in double quotes."""
    terms = []
    for phrase, word in _TERM.findall(unicodedata.normalize("NFC", query)):
        term = _fold(" ".join((phrase or word.strip('"')).split()))
        if term and term not in terms:
            terms.append(term)
    return terms


def _fold(text: str) -> str:
    """Case-fold text the same way for the query and the notes.

    The callers first put both in Unicode NFC, so an accented letter stored as a
    letter plus a combining accent (common in text from macOS) still matches.
    """
    return text.translate(_FOLD_TABLE)


def _positions(text: str) -> list[int]:
    """For each position in _fold(text), the position in text it comes from; one more at the end."""
    positions = [i for i, char in enumerate(text) for _ in _FOLD_TABLE[ord(char)]]
    positions.append(len(text))
    return positions


def node_lines(text: str, node_ids: set[str], file_node: str | None) -> dict[str, list[tuple[int, str]]]:
    """Return the lines of each node in a file, as (line number, line).

    A line belongs to the innermost heading with an ID that is in node_ids,
    otherwise to file_node (lines that belong to no node are left out).
    Property drawers and :ID: lines are left out. Inside a block
    (#+begin_src, #+begin_example, ...) lines are text, not drawers; a
    heading still ends the block, as in Org.
    """
    # Not splitlines(): it also breaks at form feed and U+2028, which would
    # shift the line numbers. read_text already turned CR and CRLF into \n.
    lines = text.split("\n")
    # The ID of each heading (by its index in lines); -1 is the file level.
    heading_ids: dict[int, str] = {}
    heading = -1
    in_drawer = False
    block = None  # The name of the block the line is in, such as "src".
    skipped = set()
    for i, line in enumerate(lines):
        if _HEADING.match(line):
            heading = i
            in_drawer = False
            block = None
        elif block:
            match = _BLOCK_END.match(line)
            if match and match.group(1).lower() == block:
                block = None
        elif in_drawer:
            skipped.add(i)
            match = _ID_LINE.match(line)
            if match and heading not in heading_ids:
                heading_ids[heading] = match.group(1)
            in_drawer = not _DRAWER_END.match(line)
        elif _DRAWER_START.match(line):
            skipped.add(i)
            in_drawer = True
        elif match := _BLOCK_START.match(line):
            block = match.group(1).lower()
        elif _ID_LINE.match(line):
            skipped.add(i)

    result: dict[str, list[tuple[int, str]]] = {}
    stack: list[tuple[int, str | None]] = []
    for i, line in enumerate(lines):
        match = _HEADING.match(line)
        if match:
            level = len(match.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            node = heading_ids.get(i)
            stack.append((level, node if node in node_ids else None))
        if i in skipped:
            continue
        owner = next((node for _, node in reversed(stack) if node), file_node)
        if owner:
            result.setdefault(owner, []).append((i + 1, line))
    return result


def search_lines(lines: list[tuple[int, str]], terms: list[str]) -> tuple[int, int, str] | None:
    """Search one node's lines for all terms.

    Returns (number of hits, line number of the first hit, snippet), or None
    when a term is missing. Whitespace is collapsed, so a phrase may go over
    the end of a line, but not over lines that were left out.
    """
    text = ""
    starts = []
    numbers = []
    previous = None
    gap = False
    for number, line in lines:
        gap = gap or (previous is not None and number != previous + 1)
        previous = number
        part = " ".join(line.split())
        if part:
            if numbers:
                text += _GAP if gap else " "
            gap = False
            starts.append(len(text))
            numbers.append(number)
            text += part
    folded = _fold(text)
    hits = 0
    first = None
    for term in terms:
        count = folded.count(term)
        if count == 0:
            return None
        hits += count
        at = folded.find(term)
        if first is None or at < first[0]:
            first = (at, len(term))
    at, length = first
    if len(folded) != len(text):
        positions = _positions(text)
        at, length = positions[at], positions[at + length - 1] + 1 - positions[at]
    start = max(0, at - max(0, SNIPPET_LENGTH - length) // 2)
    end = min(len(text), start + max(SNIPPET_LENGTH, length))
    start = max(0, min(start, end - SNIPPET_LENGTH))
    text = text.replace(_GAP, " ")
    snippet = (
        ("…" if start > 0 else "")
        + text[start:at]
        + MARK
        + text[at : at + length]
        + MARK
        + text[at + length : end]
        + ("…" if end < len(text) else "")
    )
    return hits, numbers[bisect_right(starts, at) - 1], snippet


def search_text(query: str, limit: int = 20, tag: str | None = None) -> str:
    """Search the text of the notes; see org_roam_search_text."""
    terms = parse_query(query)
    if not terms:
        return "Error: query is empty."
    if limit < 1:
        return "Error: limit must be at least 1."
    allowed = None
    # One read transaction, so all three tables are from the same moment.
    conn = db.get_connection()
    try:
        conn.execute("BEGIN")
        if tag:
            rows = db.query("SELECT DISTINCT node_id FROM tags WHERE tag = ?", (db.quote_param(tag),), conn)
            allowed = {row["node_id"] for row in rows}
        node_rows = db.query("SELECT id, title, file, level FROM nodes", conn=conn)
        file_rows = db.query("SELECT file FROM files", conn=conn)
    finally:
        conn.close()
    nodes_by_file: dict[str, list[dict]] = {}
    for row in node_rows:
        nodes_by_file.setdefault(row["file"], []).append(row)

    found = []
    unreadable = 0
    for row in file_rows:
        file = row["file"]
        nodes = nodes_by_file.get(file)
        if not nodes:
            continue
        try:
            text = unicodedata.normalize("NFC", Path(file).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            unreadable += 1
            continue
        # A node can only match when the whole file has every term.
        folded = _fold(" ".join(text.split()))
        if not all(term in folded for term in terms):
            continue
        by_id = {node["id"]: node for node in nodes}
        file_node = next((node["id"] for node in nodes if node["level"] == 0), None)
        for node_id, lines in node_lines(text, set(by_id), file_node).items():
            if allowed is not None and node_id not in allowed:
                continue
            hit = search_lines(lines, terms)
            if hit:
                hits, line, snippet = hit
                found.append((hits, by_id[node_id]["title"] or "", node_id, file, line, snippet))

    found.sort(key=lambda r: (-r[0], r[1].lower(), r[1], r[2]))
    found = found[:limit]
    if found:
        out = [f'Notes containing "{query}" ({len(found)}):']
        out += [f"{node_id} | {title} | {file}:{line} | {snippet}" for _, title, node_id, file, line, snippet in found]
    else:
        out = [f"No notes contain: {query}"]
    if unreadable:
        out.append(f"{unreadable} file{'' if unreadable == 1 else 's'} could not be read (not UTF-8, or missing).")
    return "\n".join(out)
