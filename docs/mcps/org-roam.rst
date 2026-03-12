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


Advanced Graph Analysis Tools
------------------------------

These tools compute sophisticated graph algorithms to analyze your knowledge graph
structure, identify communities, find bridge nodes, and suggest missing connections.

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Tool
     - Parameters
     - Description
   * - ``org_roam_pagerank``
     - ``limit: int = 20``
     - Compute node importance scores using PageRank algorithm
   * - ``org_roam_communities``
     - ``resolution: float = 1.0``
     - Detect topic clusters using Louvain algorithm
   * - ``org_roam_betweenness``
     - ``limit: int = 20``
     - Find bridge nodes connecting different clusters
   * - ``org_roam_closeness``
     - ``limit: int = 20``
     - Distance-based centrality scoring
   * - ``org_roam_clustering_coefficient``
     - ``node_id: str = None``
     - Measure local density (tight clusters vs bridges)
   * - ``org_roam_graph_stats``
     - (none)
     - Overall graph health metrics (density, diameter, components)
   * - ``org_roam_suggest_links``
     - ``node_id: str, limit: int = 10``
     - Link prediction via common neighbors
   * - ``org_roam_connected_components``
     - (none)
     - Identify isolated subgraphs needing integration

**Algorithm Details:**

- **PageRank:** Eigenvector-based importance (nodes with high-quality incoming links score higher)
- **Louvain:** Community detection via modularity optimization (finds natural topic clusters)
- **Betweenness Centrality:** Identifies synthesis points (nodes connecting disparate clusters)
- **Closeness Centrality:** Average distance-based scoring (central hubs in graph structure)
- **Clustering Coefficient:** Local density measurement (0-1, high = tight cluster, low = bridge)
- **Graph Stats:** Density, diameter, components, average degree, modularity
- **Link Suggestion:** Jaccard similarity via common neighbors (identifies unlinked nodes that should connect)
- **Connected Components:** Weakly connected subgraphs (treats graph as undirected for connectivity)

Requirements
------------

- Python 3.10+
- ``mcp`` package (installed via ``uv pip install mcp``)
- ``networkx>=3.0`` (for advanced graph algorithms)
- ``python-louvain>=0.16`` (for community detection)
- ``scipy>=1.10`` (for PageRank computation)
- Emacs with ``(server-start)`` for write tools and ``emacs_eval``
- Read tools work without Emacs — they query SQLite directly


Claude Code Setup
-----------------

Register the server using the Claude Code CLI.
Prefer ``--scope user`` if you want org-roam available in all projects.

.. code-block:: bash

    # Available in all Claude Code projects
    claude mcp add --scope user org-roam -- \
      uv run --no-config --directory /path/to/cgeng-ai-skills python -m mcps.org_roam.server

To enable it only for the current project:

.. code-block:: bash

    claude mcp add --scope local org-roam -- \
      uv run --no-config --directory /path/to/cgeng-ai-skills python -m mcps.org_roam.server


Verification
------------

.. code-block:: bash

    claude mcp list

You should see ``org-roam`` listed as connected.

In a Claude Code chat session,
try a quick call:

.. code-block:: text

    org_roam_find("search term")


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

.. dropdown:: Getting the DB path from a running Emacs server

   If you have a running Emacs server (``M-x server-start``),
   you can query the effective org-roam database path via ``emacsclient``.

   .. code-block:: bash

       # Prints the org-roam DB path (usually quoted)
       emacsclient --eval '(org-roam-db-location)'

       # Export ORG_ROAM_DB from Emacs (strips surrounding quotes)
       export ORG_ROAM_DB=$(emacsclient --eval '(org-roam-db-location)' | tr -d '"')


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
    ├── server.py           # FastMCP entry point
    ├── db.py               # SQLite connection + DB detection
    ├── emacs.py            # emacsclient wrapper
    ├── queries.py          # SQL templates
    ├── tools_emacs.py      # Layer 1: emacs_eval
    ├── tools_roam.py       # Layer 2: org-roam tools
    └── tools_advanced.py   # Layer 3: advanced graph algorithms (networkx)
