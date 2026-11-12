"""org_roam_search_text: search the text of the notes, not only their titles.

The files are the ones in the database's `files` table. Each call reads
them once; there is no index.
"""

from bisect import bisect_right
from pathlib import Path
import re

from . import db


SNIPPET_LENGTH = 120
MARK = "**"
_TERM = re.compile(r'"([^"]*)"|(\S+)')
_HEADING = re.compile(r"^(\*+)\s")
_ID_LINE = re.compile(r"^\s*:ID:\s*(\S+)\s*$", re.IGNORECASE)
_DRAWER_START = re.compile(r"^\s*:PROPERTIES:\s*$", re.IGNORECASE)
_DRAWER_END = re.compile(r"^\s*:END:\s*$", re.IGNORECASE)


def parse_query(query: str) -> list[str]:
    """Split a query into lower-case terms: words, and phrases in double quotes."""
    terms = []
    for phrase, word in _TERM.findall(query):
        term = " ".join((phrase or word.strip('"')).split()).lower()
        if term and term not in terms:
            terms.append(term)
    return terms


def _fold(text: str) -> str:
    """Lower-case text without changing its length, so positions stay the same."""
    low = text.lower()
    if len(low) == len(text):
        return low
    return "".join(low if len(low := c.lower()) == 1 else c for c in text)


def node_lines(text: str, node_ids: set[str], file_node: str | None) -> dict[str, list[tuple[int, str]]]:
    """Return the lines of each node in a file, as (line number, line).

    A line belongs to the innermost heading with an ID that is in node_ids,
    otherwise to file_node (lines that belong to no node are left out).
    Property drawers and :ID: lines are left out.
    """
    lines = text.splitlines()
    # The ID of each heading (by its index in lines); -1 is the file level.
    heading_ids: dict[int, str] = {}
    heading = -1
    in_drawer = False
    skipped = set()
    for i, line in enumerate(lines):
        if in_drawer:
            skipped.add(i)
            match = _ID_LINE.match(line)
            if match and heading not in heading_ids:
                heading_ids[heading] = match.group(1)
            in_drawer = not _DRAWER_END.match(line)
        elif _DRAWER_START.match(line):
            skipped.add(i)
            in_drawer = True
        elif _HEADING.match(line):
            heading = i
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
    the end of a line.
    """
    parts = []
    starts = []
    numbers = []
    offset = 0
    for number, line in lines:
        part = " ".join(line.split())
        if not part:
            continue
        parts.append(part)
        starts.append(offset)
        numbers.append(number)
        offset += len(part) + 1
    text = " ".join(parts)
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
    start = max(0, at - max(0, SNIPPET_LENGTH - length) // 2)
    end = min(len(text), start + max(SNIPPET_LENGTH, length))
    start = max(0, min(start, end - SNIPPET_LENGTH))
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
    allowed = None
    if tag:
        rows = db.query("SELECT DISTINCT node_id FROM tags WHERE tag = ?", (db.quote_param(tag),))
        allowed = {row["node_id"] for row in rows}
    nodes_by_file: dict[str, list[dict]] = {}
    for row in db.query("SELECT id, title, file, level FROM nodes"):
        nodes_by_file.setdefault(row["file"], []).append(row)

    found = []
    unreadable = 0
    for row in db.query("SELECT file FROM files"):
        file = row["file"]
        nodes = nodes_by_file.get(file)
        if not nodes:
            continue
        try:
            text = Path(file).read_text(encoding="utf-8")
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
    found = found[: max(0, limit)]
    if found:
        out = [f'Notes containing "{query}" ({len(found)}):']
        out += [f"{node_id} | {title} | {file}:{line} | {snippet}" for _, title, node_id, file, line, snippet in found]
    else:
        out = [f"No notes contain: {query}"]
    if unreadable:
        out.append(f"{unreadable} file{'' if unreadable == 1 else 's'} could not be read (not UTF-8, or missing).")
    return "\n".join(out)
