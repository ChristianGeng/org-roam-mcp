# org-roam MCP server

An MCP server that gives AI agents access to an
[org-roam](https://www.orgroam.com/) knowledge graph.

Reads query the org-roam SQLite database directly, so they work without
Emacs. `org_roam_sync` and `emacs_eval` go through `emacsclient` and need a
running Emacs server (`M-x server-start`).

```text
AI client → MCP server (Python, stdio) → sqlite3 (reads)
                                        → emacsclient --eval (sync, Elisp)
```

## Tools

| Tool | Parameters | Purpose |
|------|------------|---------|
| `org_roam_find` | `search` | Find nodes by title substring |
| `org_roam_read_node` | `node_id` | Read the full file of a node |
| `org_roam_backlinks` | `node_id` | All nodes that link to a node |
| `org_roam_bfs` | `node_id, depth=2` | Breadth-first neighbourhood of a node |
| `org_roam_shortest_path` | `start_id, end_id` | Shortest paths between two nodes (max depth 8) |
| `org_roam_common_neighbors` | `node_a, node_b` | Neighbours two nodes share |
| `org_roam_central` | `limit=20` | Most connected nodes by degree |
| `org_roam_orphans` | | Nodes without links |
| `org_roam_sync` | | Run `org-roam-db-sync` in Emacs |
| `emacs_eval` | `expr` | Evaluate any Elisp through `emacsclient` |

Graph algorithms (networkx; only `id:` links count):

| Tool | Parameters | Purpose |
|------|------------|---------|
| `org_roam_pagerank` | `limit=20` | Node importance by PageRank |
| `org_roam_communities` | `resolution=1.0` | Topic clusters by Louvain community detection |
| `org_roam_betweenness` | `limit=20` | Bridge nodes between clusters |
| `org_roam_closeness` | `limit=20` | Distance-based centrality |
| `org_roam_clustering_coefficient` | `node_id=None` | Local density of a node or the whole graph |
| `org_roam_graph_stats` | | Density, diameter, components, average degree |
| `org_roam_suggest_links` | `node_id, limit=10` | Unlinked nodes with many shared neighbours |
| `org_roam_connected_components` | | Weakly connected subgraphs |

Worked examples: [docs/examples.md](docs/examples.md).

## Install

Needs Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:ChristianGeng/org-roam-mcp.git ~/work/myfiles/org-roam-mcp
uv sync --no-config --directory ~/work/myfiles/org-roam-mcp
```

## Register with Claude Code

```bash
claude mcp add --scope user org-roam -- \
  uv run --no-config --directory ~/work/myfiles/org-roam-mcp org-roam-mcp
```

`--no-config` ignores custom package indexes from a surrounding uv config,
which may be unreachable (for example off VPN). After the first `uv sync`
the server starts offline.

Without a clone, uv can also fetch and run it. This needs network on first
use, and GitHub access over SSH while the repo is private:

```bash
claude mcp add --scope user org-roam -- \
  uvx --no-config --from git+ssh://git@github.com/ChristianGeng/org-roam-mcp.git org-roam-mcp
```

## Update

```bash
git -C ~/work/myfiles/org-roam-mcp pull
uv sync --no-config --directory ~/work/myfiles/org-roam-mcp
```

Then restart the client (in Claude Code, `/mcp` and reconnect). With `uvx`,
add `--refresh` once to fetch the new version.

Check with `claude mcp list`; then in a session ask for
`org_roam_find("some title")`.

## Other clients

VS Code (`.vscode/mcp.json`), Windsurf (`~/.codeium/windsurf/mcp_config.json`)
and other clients take the same command:

```json
{
  "servers": {
    "org-roam": {
      "command": "uv",
      "args": ["run", "--no-config", "--directory",
               "/path/to/org-roam-mcp", "org-roam-mcp"]
    }
  }
}
```

(Windsurf and Claude's JSON config call the key `mcpServers`.)

## Finding the database

The server uses the first of:

1. `org-roam-db-location` from the running Emacs (`emacsclient`);
2. the `ORG_ROAM_DB` environment variable;
3. `~/doom-emacs/.local/cache/org-roam.db`, `~/emacs-conf/org-roam.db`,
   `~/.emacs.d/org-roam.db`, `~/.emacs.d/.local/cache/org-roam.db`,
   `~/.config/emacs/org-roam.db`, `~/.local/share/emacs/org-roam.db`.

Each candidate must have org-roam's `files` and `nodes` tables.

## Development

```bash
uv run pytest
uvx ruff check .
```

Moved out of `cgeng-ai-skills` (`mcps/org_roam`) with its history.

## Licence

MIT, see [LICENSE](LICENSE).
