# org-roam MCP Server

MCP server that gives AI agents access to your [org-roam](https://www.orgroam.com/) knowledge graph.

Requires a running Emacs server (`M-x server-start`).

## Tools

| Tool | Purpose |
|------|---------|
| `org_roam_find` | Find nodes by title substring |
| `org_roam_read_node` | Read the full content of a node file |
| `org_roam_backlinks` | Find all nodes that link to a given node |
| `org_roam_bfs` | BFS traversal from a node (configurable depth) |
| `org_roam_shortest_path` | Find shortest paths between two nodes |
| `org_roam_common_neighbors` | Find shared neighbors of two nodes |
| `org_roam_central` | Find the most connected nodes by degree |
| `org_roam_orphans` | Find nodes with no links |
| `org_roam_sync` | Sync the org-roam database |
| `emacs_eval` | Evaluate arbitrary Elisp via emacsclient |

## Prerequisites

- Emacs with org-roam configured and `M-x server-start`
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management

## Installation

Clone the repo and sync dependencies:

```bash
git clone <repo-url> ~/work/cgeng/cgeng-ai-skills
cd ~/work/cgeng/cgeng-ai-skills
uv sync
```

## Configuring for Claude Code

Add to your Claude config (e.g. `~/.claude-personal/.claude.json`):

```json
{
  "mcpServers": {
    "org-roam": {
      "command": "uv",
      "args": [
        "run",
        "--no-config",
        "--directory", "/path/to/cgeng-ai-skills",
        "python", "-m", "mcps.org_roam.server"
      ]
    }
  }
}
```

Or via CLI:

```bash
claude mcp add org-roam -- uv run --no-config --directory /path/to/cgeng-ai-skills python -m mcps.org_roam.server
```

## Configuring for VS Code (GitHub Copilot)

No built-in CLI for MCP — edit the JSON manually or use Command Palette → "MCP: Add Server".

Create or edit `.vscode/mcp.json` in your project:

```json
{
  "inputs": [],
  "servers": {
    "org-roam": {
      "command": "uv",
      "args": [
        "run",
        "--no-config",
        "--directory", "/path/to/cgeng-ai-skills",
        "python", "-m", "mcps.org_roam.server"
      ]
    }
  }
}
```

Or add to your user-level VS Code `settings.json` for access in all workspaces:

```json
{
  "mcp": {
    "servers": {
      "org-roam": {
        "command": "uv",
        "args": [
          "run",
          "--no-config",
          "--directory", "/path/to/cgeng-ai-skills",
          "python", "-m", "mcps.org_roam.server"
        ]
      }
    }
  }
}
```

After saving, click "Start" above the server definition in VS Code,
or restart Copilot Chat.

## Configuring for Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "org-roam": {
      "command": "uv",
      "args": [
        "run",
        "--no-config",
        "--directory", "/path/to/cgeng-ai-skills",
        "python", "-m", "mcps.org_roam.server"
      ]
    }
  }
}
```

Enable MCP in Windsurf: Settings > Advanced > Cascade > Model Context Protocol.

## Verifying

In any client, try calling:

```
org_roam_find("search term")
org_roam_central(limit=5)
```

If you get results, the server is connected and your org-roam database is accessible.

## Notes

- `--no-config` bypasses any custom PyPI indexes that may be unreachable off-VPN.
- The server communicates via stdio (standard MCP transport).
- The org-roam SQLite database is read from `~/.emacs.d/.local/cache/org-roam.db`
  (Doom Emacs default). Other Emacs distributions may differ.
