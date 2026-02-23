Org-Roam MCP Server
===================

A local MCP server that connects Claude Code to your org-roam knowledge graph
and Doom Emacs.

Read operations query the org-roam SQLite database directly.
Write operations and arbitrary Elisp go through ``emacsclient``.


Architecture
------------

.. code-block:: text

    Claude Code → MCP server (Python, stdio) → sqlite3 (reads)
                                              → emacsclient --eval (writes, Elisp)
                                              → Doom Emacs

Two layers:

1. **emacs_eval** — general Emacs bridge.
   Runs any Elisp expression via ``emacsclient --eval``.
2. **org-roam tools** — typed, high-level operations
   against the org-roam database.


Tools
-----

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Tool
     - Parameters
     - Description
   * - ``emacs_eval``
     - ``expr: str``
     - Run arbitrary Elisp via emacsclient
   * - ``org_roam_find``
     - ``search: str``
     - Find nodes by title substring
   * - ``org_roam_backlinks``
     - ``node_id: str``
     - All nodes linking to a given node
   * - ``org_roam_bfs``
     - ``node_id: str, depth: int = 2``
     - BFS neighbourhood traversal
   * - ``org_roam_shortest_path``
     - ``start_id: str, end_id: str``
     - Shortest paths between two nodes (max depth 8)
   * - ``org_roam_common_neighbors``
     - ``node_a: str, node_b: str``
     - Common neighbors (synthesis candidates)
   * - ``org_roam_central``
     - ``limit: int = 20``
     - Most connected nodes by degree centrality
   * - ``org_roam_orphans``
     - (none)
     - Nodes with no links
   * - ``org_roam_read_node``
     - ``node_id: str``
     - Read full file content of a node
   * - ``org_roam_sync``
     - (none)
     - Sync the org-roam database


Requirements
------------

- Python 3.10+
- ``mcp`` package (installed via ``uv pip install mcp``)
- Emacs with ``(server-start)`` for write tools and ``emacs_eval``
- Read tools work without Emacs — they query SQLite directly


Database Detection
------------------

The server locates ``org-roam.db`` in this order:

1. ``ORG_ROAM_DB`` environment variable
2. ``emacsclient --eval "org-roam-db-location"``
3. Filesystem fallbacks:

   - ``~/emacs-conf/org-roam.db``
   - ``~/doom-emacs/.local/cache/org-roam.db``
   - ``~/.emacs.d/org-roam.db``
   - ``~/.emacs.d/.local/cache/org-roam.db``
   - ``~/.config/emacs/org-roam.db``
   - ``~/.local/share/emacs/org-roam.db``


Registration
------------

Registered globally in ``~/.claude.json``:

.. code-block:: json

    {
      "mcpServers": {
        "org-roam": {
          "command": "uv",
          "args": [
            "run", "--no-config", "--directory",
            "/home/cgeng/work/cgeng/cgeng-ai-skills",
            "python", "-m", "mcps.org_roam.server"
          ]
        }
      }
    }

The ``--no-config`` flag bypasses the project's custom PyPI index,
which requires VPN.


Usage Examples
--------------

In a Claude Code session,
ask in natural language:

- "Find my notes about attention" → ``org_roam_find``
- "Show the neighborhood around this node" → ``org_roam_bfs``
- "What links to this node?" → ``org_roam_backlinks``
- "How are these two nodes connected?" → ``org_roam_shortest_path``
- "What are the most connected nodes?" → ``org_roam_central``
- "Find orphan nodes" → ``org_roam_orphans``
- "Read node X" → ``org_roam_read_node``
- "Sync the database" → ``org_roam_sync``
- "Evaluate (+ 1 2) in Emacs" → ``emacs_eval``


  You: "Research flash attention v2 and add it to my knowledge graph"

  Claude:  1. web search / perplexity  →  gathers content
           2. org_roam_find("flash")   →  checks for duplicates
           3. org_roam_add_node(...)   →  creates the .org file, links parent, syncs DB

Source
------

.. code-block:: text

    mcps/org_roam/
    ├── __init__.py
    ├── server.py        # FastMCP entry point
    ├── db.py            # SQLite connection + DB detection
    ├── emacs.py         # emacsclient wrapper
    ├── queries.py       # SQL templates
    ├── tools_emacs.py   # Layer 1: emacs_eval
    └── tools_roam.py    # Layer 2: org-roam tools
