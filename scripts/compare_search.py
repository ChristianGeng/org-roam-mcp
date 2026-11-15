"""Compare the text search with the search by meaning on your own questions.

    uv run --extra semantic scripts/compare_search.py questions.txt

The questions file has one question per line. After a "|" it may list the
IDs of the notes that should be found (separated by spaces or commas); then
recall@10 is printed: the share of those IDs in each search's top 10.
Empty lines and lines starting with "#" are skipped. For example:

    # question | expected node IDs
    how do I keep the soil moist | 1f0c... 9a2e...
    Wann wird der Kürbis geerntet?

For each question the top 10 of org_roam_search_text and of
org_roam_search_similar are printed side by side (an expected ID is marked
with *), then the time to index (embed new and changed files) and to answer.
The text search needs every word of the question in a node, so a whole
sentence often finds nothing there; that is part of what is compared.

The database is found as by the server (a running Emacs, ORG_ROAM_DB, or the
standard places); the model is ORG_ROAM_MCP_EMBED_MODEL or the default.
"""

import argparse
from dataclasses import dataclass
from dataclasses import field
import re
import sys
import time

from org_roam_mcp import db
from org_roam_mcp import search_text
from org_roam_mcp import semantic


WIDTH = 50


@dataclass
class Question:
    text: str
    expected: list[str] = field(default_factory=list)


def read_questions(path: str) -> list[Question]:
    """Read the questions file (see the module docstring)."""
    questions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            text, _, ids = line.partition("|")
            questions.append(Question(text.strip(), [i for i in re.split(r"[\s,]+", ids) if i]))
    return questions


def text_hits(query: str, limit: int, tag: str | None) -> list[tuple[str, str]]:
    """Return the text search's result as (id, title)."""
    result = search_text.search_text(query, limit, tag)
    return [tuple(line.split(" | ")[:2]) for line in result.splitlines()[1:] if " | " in line]


def recall(found: list[str], expected: list[str]) -> float:
    """Return the share of expected IDs that are in found."""
    return sum(1 for i in set(expected) if i in found) / len(set(expected))


def _cell(hit: tuple[str, str] | None, expected: list[str]) -> str:
    if hit is None:
        return ""
    node_id, title = hit
    mark = "*" if node_id in expected else " "
    cell = f"{mark}{title} ({node_id})"
    return cell if len(cell) <= WIDTH else cell[: WIDTH - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("questions", help="file with one question per line, optionally | expected IDs")
    parser.add_argument("--limit", type=int, default=10, help="results per search (default 10)")
    parser.add_argument("--tag", help="only nodes with this tag")
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    questions = read_questions(args.questions)
    if not questions:
        print("No questions in the file.", file=sys.stderr)
        return 1
    embedder = semantic.get_embedder()
    print(f"Database: {db.detect_db()}")
    print(f"Model: {embedder.model}; cache: {semantic.cache_dir() / semantic.CACHE_FILE}")

    # Load the model first (and download it, the first time), so that this
    # does not count as the time to index or to answer.
    start = time.perf_counter()
    embedder.encode([embedder.query_prefix + "warm-up"])
    print(f"Model loaded: {time.perf_counter() - start:.1f} s")

    start = time.perf_counter()
    cache, stats, *_ = semantic.index(embedder)
    cache.close()
    print(
        f"Index: {time.perf_counter() - start:.1f} s; {stats.files} files, {stats.embedded} embedded now "
        f"({stats.pieces} pieces), {stats.unreadable} unreadable, {stats.dropped} dropped from the cache"
    )

    times = {"text": [], "similar": []}
    recalls = {"text": [], "similar": []}
    for n, question in enumerate(questions, 1):
        start = time.perf_counter()
        text = text_hits(question.text, args.limit, args.tag)
        times["text"].append(time.perf_counter() - start)
        start = time.perf_counter()
        hits, _ = semantic.similar(question.text, args.limit, args.tag, embedder)
        times["similar"].append(time.perf_counter() - start)
        similar = [(hit.node_id, hit.title) for hit in hits]

        print(f"\n{n}. {question.text}")
        print(f"   {'#':>2}  {'text search':<{WIDTH}}  by meaning")
        for rank in range(max(len(text), len(similar), 1)):
            left = _cell(text[rank] if rank < len(text) else None, question.expected)
            right = _cell(similar[rank] if rank < len(similar) else None, question.expected)
            print(f"   {rank + 1:>2}  {left or ('(nothing)' if rank == 0 else ''):<{WIDTH}}  {right}")
        line = f"   time: text {times['text'][-1]:.2f} s, by meaning {times['similar'][-1]:.2f} s"
        if question.expected:
            for name, found in (("text", text), ("similar", similar)):
                recalls[name].append(recall([node_id for node_id, _ in found], question.expected))
            line += f"; recall@{args.limit}: text {recalls['text'][-1]:.2f}, by meaning {recalls['similar'][-1]:.2f}"
        print(line)

    print(f"\nSummary over {len(questions)} questions:")
    for name, label in (("text", "text search"), ("similar", "by meaning")):
        mean_time = sum(times[name]) / len(times[name])
        summary = f"  {label}: mean time {mean_time:.2f} s"
        if recalls[name]:
            mean = sum(recalls[name]) / len(recalls[name])
            summary += f", mean recall@{args.limit} {mean:.2f} ({len(recalls[name])} questions with IDs)"
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
