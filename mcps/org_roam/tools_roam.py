"""Layer 2: Org-roam specific tools with typed parameters."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import queries
from . import tools_advanced
from .db import query
from .db import quote_param
from .emacs import emacs_eval


def register(mcp: FastMCP) -> None:
    """Register all org-roam tools."""

    @mcp.tool()
    def org_roam_find(search: str) -> list[dict]:
        """Find org-roam nodes by title substring.

        Args:
            search: Title fragment to search for (case-insensitive)
        """
        return query(queries.FIND, (search,))

    @mcp.tool()
    def org_roam_backlinks(node_id: str) -> list[dict]:
        """Find all nodes that link to the given node.

        Args:
            node_id: UUID of the target node
        """
        return query(queries.BACKLINKS, (quote_param(node_id),))

    @mcp.tool()
    def org_roam_bfs(node_id: str, depth: int = 2) -> list[dict]:
        """BFS neighbourhood traversal from a node.

        Returns all nodes reachable within `depth` hops.

        Args:
            node_id: UUID of the starting node
            depth: Maximum traversal depth (default 2)
        """
        qid = quote_param(node_id)
        return query(queries.BFS, (qid, qid, depth, qid))

    @mcp.tool()
    def org_roam_shortest_path(start_id: str, end_id: str) -> list[dict]:
        """Find shortest paths between two nodes (up to 3, max depth 8).

        Returns paths with resolved titles.

        Args:
            start_id: UUID of the start node
            end_id: UUID of the end node
        """
        qs = quote_param(start_id)
        qe = quote_param(end_id)
        rows = query(queries.SHORTEST_PATH, (qs, qs, qe))
        if not rows:
            return [{"message": "No path found between the two nodes (within depth 8)."}]

        results = []
        for row in rows:
            # Path is a concatenation of quoted IDs joined by commas.
            # After _strip_elisp_quotes on the full string, split and clean.
            raw = row["path"].strip('"')
            path_ids = [uid.strip('"') for uid in raw.split('","')]
            steps = []
            for uid in path_ids:
                title_rows = query(queries.RESOLVE_TITLE, (quote_param(uid),))
                title = title_rows[0]["title"] if title_rows else "[unknown]"
                steps.append({"id": uid, "title": title})
            results.append({"hops": row["depth"], "path": steps})
        return results

    @mcp.tool()
    def org_roam_common_neighbors(node_a: str, node_b: str) -> list[dict]:
        """Find common neighbors of two nodes (synthesis candidates).

        Args:
            node_a: UUID of the first node
            node_b: UUID of the second node
        """
        qa = quote_param(node_a)
        qb = quote_param(node_b)
        return query(queries.COMMON_NEIGHBORS, (qa, qa, qb))

    @mcp.tool()
    def org_roam_central(limit: int = 20) -> list[dict]:
        """Find the most central nodes by degree centrality.

        Args:
            limit: Number of top nodes to return (default 20)
        """
        return query(queries.CENTRAL, (limit,))

    @mcp.tool()
    def org_roam_orphans() -> list[dict]:
        """Find orphan nodes with no incoming or outgoing links."""
        return query(queries.ORPHANS)

    @mcp.tool()
    def org_roam_read_node(node_id: str) -> str:
        """Read the full content of an org-roam node file.

        Args:
            node_id: UUID of the node to read
        """
        rows = query("SELECT file FROM nodes WHERE id = ?", (quote_param(node_id),))
        if not rows:
            return f"Error: No node found with id {node_id}"
        filepath = rows[0]["file"]
        path = Path(filepath)
        if not path.is_file():
            return f"Error: File not found: {filepath}"
        return path.read_text(encoding="utf-8")

    @mcp.tool()
    def org_roam_sync() -> str:
        """Sync the org-roam database. Requires a running Emacs server."""
        result, error = emacs_eval("(org-roam-db-sync)")
        if error:
            return f"Error: {error}"
        return "org-roam database synced successfully."

    # Register advanced graph analysis tools
    tools_advanced.register(mcp)
