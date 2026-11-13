# org-roam MCP server

An MCP server that gives AI agents access to an
[org-roam](https://www.orgroam.com/) knowledge graph.

It needs no API key: the AI client brings the model. Reads query the
org-roam SQLite database directly, so they work without Emacs.
`org_roam_sync` and `emacs_eval` go through `emacsclient` and need a
running Emacs server (`M-x server-start`).

```text
AI client → MCP server (Python, stdio) → sqlite3 (reads)
                                        → emacsclient --eval (sync, Elisp)
```

## Tools

| Tool | Parameters | Purpose |
|------|------------|---------|
| `org_roam_find` | `search` | Find nodes by title substring |
| `org_roam_search_text` | `query, limit=20, tag=None` | Find nodes by the words in their text |
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

`org_roam_search_text` searches the text of the files in the database:
all words must occur in a node, in any order, case ignored (ß matches ss),
and a phrase in double quotes counts as one word. Parts of words match too:
`tomato` finds `tomatoes`, and `art` finds `party`. It returns one line per node (the heading
node the hit is under, otherwise the file's node): `id | title | file:line |
snippet`, with the hit marked as `**hit**`, most hits first. Property
drawers are not searched. Files that are not UTF-8 are skipped and counted.
It has no index: each call reads the files once. With 1,000 synthetic notes
(5 MB) a call took 0.2–0.7 s; with 5,000 (24 MB), 1 s for a rare word and
about 4 s for a word found in most files. An index (for example SQLite FTS5, as in the
roam-graph-mobile app) would be worth it when calls get slow with many more
notes.

Worked examples: [docs/examples.md](docs/examples.md).

## Install

Needs Python 3.10+ and [uv](https://docs.astral.sh/uv/). The repository is
public, so no GitHub account is needed.

The simplest way: let uv fetch and run it, and register it with Claude Code
in one line.

```bash
claude mcp add --scope user org-roam -- \
  uvx --no-config --from git+https://github.com/ChristianGeng/org-roam-mcp org-roam-mcp
```

This needs a network connection the first time. To use a release instead of
the newest code, add the tag: `…/org-roam-mcp@v0.1.0`.

Check that it installs and which version runs:

```bash
uvx --no-config --from git+https://github.com/ChristianGeng/org-roam-mcp org-roam-mcp --version
uvx --no-config --from git+https://github.com/ChristianGeng/org-roam-mcp org-roam-mcp --help
```

`--help` also explains how the database is found. Without arguments the
command starts the server, which then waits for an MCP client on standard
input; that is what Claude Code does, so it is not run by hand.

`--no-config` ignores custom package indexes from a surrounding uv config,
which may be unreachable (for example off a company VPN).

### From a local clone

A clone starts offline after the first `uv sync`. Any folder works, for
example `~/src/org-roam-mcp`:

```bash
git clone https://github.com/ChristianGeng/org-roam-mcp.git ~/src/org-roam-mcp
uv sync --no-config --directory ~/src/org-roam-mcp
claude mcp add --scope user org-roam -- \
  uv run --no-config --directory ~/src/org-roam-mcp org-roam-mcp
```

## Update

With `uvx`, add `--refresh` once to fetch the new version. With a clone:

```bash
git -C ~/src/org-roam-mcp pull
uv sync --no-config --directory ~/src/org-roam-mcp
```

Then restart the client (in Claude Code, `/mcp` and reconnect).

Check with `claude mcp list`; then in a session ask for
`org_roam_find("some title")`.

## Other clients

The server uses no API keys and no model of its own. The client (Claude
Code, OpenCode, an editor) brings the model and its key; the server only
reads the local org-roam database and, for `org_roam_sync` and
`emacs_eval`, talks to the local Emacs.

### OpenCode

Add the server as a local MCP server, either with OpenCode's command:

```bash
opencode mcp add org-roam -- \
  uvx --no-config --from git+https://github.com/ChristianGeng/org-roam-mcp org-roam-mcp
```

or by hand in OpenCode's config: `opencode.json` (or `opencode.jsonc`) in a
project, or `~/.config/opencode/opencode.json` for every project. With
OpenCode's current config format (V2), local servers go under
`mcp.servers`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "org-roam": {
        "type": "local",
        "command": ["uvx", "--no-config", "--from",
                    "git+https://github.com/ChristianGeng/org-roam-mcp",
                    "org-roam-mcp"],
        "environment": {
          "ORG_ROAM_DB": "/home/you/.config/emacs/.local/cache/org-roam.db"
        }
      }
    }
  }
}
```

`environment` is only needed when Emacs is not running and the database is
not in a standard place (see [Finding the database](#finding-the-database));
otherwise leave it out. With the command, pass it as
`opencode mcp add org-roam --env ORG_ROAM_DB=… -- uvx …`. The older V1
format puts `"org-roam"` directly under `"mcp"` (with `"enabled": true`
instead of `"disabled"`); OpenCode still reads it. See OpenCode's
[MCP servers](https://opencode.ai/docs/mcp-servers/) and
[config](https://opencode.ai/docs/config/) pages.

### VS Code, Windsurf and others

VS Code (`.vscode/mcp.json`), Windsurf (`~/.codeium/windsurf/mcp_config.json`)
and other clients take the same command:

```json
{
  "servers": {
    "org-roam": {
      "command": "uvx",
      "args": ["--no-config", "--from",
               "git+https://github.com/ChristianGeng/org-roam-mcp",
               "org-roam-mcp"]
    }
  }
}
```

(Windsurf and Claude's JSON config call the key `mcpServers`.)

## Finding the database

The server uses the first of these that holds an org-roam database (one
with org-roam's `files` and `nodes` tables):

1. **A running Emacs.** The server asks it for `org-roam-db-location`
   through `emacsclient`: first the default server (`emacsclient` itself
   reads `EMACS_SERVER_FILE`), then the server named by
   `EMACS_SOCKET_NAME` if it is set, then the default sockets
   `/run/user/<uid>/emacs/server` and `/tmp/emacs<uid>/server`. Emacs
   needs `(server-start)` and org-roam loaded.
2. **`ORG_ROAM_DB`,** the full path of `org-roam.db`.
3. **The standard places** of vanilla Emacs and Doom Emacs:
   - `~/.emacs.d/org-roam.db`
   - `~/.emacs.d/.local/cache/org-roam.db`
   - `$XDG_CONFIG_HOME/emacs/org-roam.db`
   - `$XDG_CONFIG_HOME/emacs/.local/cache/org-roam.db`

   `$XDG_CONFIG_HOME` is `~/.config` when it is not set.

If your database is somewhere else and Emacs is not running, set
`ORG_ROAM_DB`, for example in the client's command:

```bash
claude mcp add --scope user org-roam -e ORG_ROAM_DB="$HOME/path/to/org-roam.db" -- \
  uvx --no-config --from git+https://github.com/ChristianGeng/org-roam-mcp org-roam-mcp
```

**An Emacs server with another name** (`server-name`) is found when
`EMACS_SOCKET_NAME` is set for the MCP server: the server passes it to
`emacsclient` as `--socket-name`, so this works with any Emacs version
(`emacsclient` reads the variable itself only from Emacs 27 on). **A TCP
server** (`server-use-tcp`) is found when `EMACS_SERVER_FILE` is set.
Otherwise use `ORG_ROAM_DB`.

If nothing is found, the error lists every place that was tried, in this
order, and says how to fix it. A database that was found is used for 60
seconds without looking again, so an Emacs that does not answer does not
slow down every query.

## Skills

Skills are instructions for an AI agent that use this server's tools. They
live next to the server in `skills/`; the server itself does not change.

### org-roam-infographic

`skills/org-roam-infographic/` tells the agent how to make an infographic
from org-roam notes **with code**: it reads the notes through this server,
takes every number and date only from the notes, picks a form (timeline,
bar or line chart, comparison, process, map of linked notes), and draws
one SVG file (or one self-contained HTML file when it needs interaction).
It checks the file with `check_svg.py`, renders it once to look at it, and
saves it next to the note without overwriting anything. It sends nothing
anywhere: no image API, no upload. Image models draw text and numbers
badly; code draws them exactly, and the file can be edited later.

See the [synthetic example](docs/examples.md#infographic-skill-a-synthetic-example).

**Claude Code** reads skills from `~/.claude/skills/` (all projects) or
`.claude/skills/` (one project). Link the skill folder there, for example
from a local clone:

```bash
mkdir -p ~/.claude/skills
ln -s ~/src/org-roam-mcp/skills/org-roam-infographic ~/.claude/skills/org-roam-infographic
```

**OpenCode** reads the same `SKILL.md` files. It looks in
`~/.config/opencode/skills/` and `.opencode/skills/`, and also in
`~/.claude/skills/` and `.claude/skills/`, so the link above works for both
(see OpenCode's [skills](https://opencode.ai/docs/skills/) page). To link it
for OpenCode only:

```bash
mkdir -p ~/.config/opencode/skills
ln -s ~/src/org-roam-mcp/skills/org-roam-infographic ~/.config/opencode/skills/org-roam-infographic
```

The skill needs this MCP server to be set up in the same client (see
[Install](#install) and [Other clients](#other-clients)), and Python 3.10+
for `check_svg.py`. After `git pull` in the clone, the linked skill is up to
date.

## Development

```bash
uv run pytest
uvx ruff check .
```

Moved out of `cgeng-ai-skills` (`mcps/org_roam`) with its history.

## Licence

MIT, see [LICENSE](LICENSE).
