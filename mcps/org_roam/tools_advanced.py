"""Advanced graph analysis tools for org-roam MCP.

Provides sophisticated graph algorithms including PageRank, community detection,
centrality measures, and link prediction using networkx.
"""

import networkx as nx
from mcp.server.fastmcp import FastMCP
from . import db
from . import queries


def _load_graph_from_db():
    """Load org-roam graph from SQLite into networkx DiGraph.

    Returns:
        nx.DiGraph: Directed graph with nodes and edges from org-roam database.
    """
    G = nx.DiGraph()

    # Get all nodes
    nodes_result = db.query(queries.GET_ALL_NODES, ())
    node_by_id = {}

    for row in nodes_result:
        node_id = db._strip_elisp_quotes(row["id"])
        title = row["title"]
        file_path = row["file"]

        G.add_node(node_id, title=title, file=file_path)
        node_by_id[node_id] = {"title": title, "file": file_path}

    # Get all ID-based links (org-roam links only)
    links_result = db.query(queries.GET_ALL_LINKS, ())

    for row in links_result:
        source = db._strip_elisp_quotes(row["source"])
        dest = db._strip_elisp_quotes(row["dest"])
        link_type = db._strip_elisp_quotes(row["type"])

        # Only include org-roam ID links
        if link_type == "id":
            G.add_edge(source, dest)

    return G, node_by_id


def register(mcp: FastMCP) -> None:
    """Register advanced graph analysis tools with MCP server."""

    @mcp.tool()
    def org_roam_pagerank(limit: int = 20) -> list[dict]:
        """Compute PageRank node importance scores.

        PageRank measures node importance based on incoming link quality.
        Nodes with links from high-importance nodes score higher.

        Args:
            limit: Number of top-ranked nodes to return (default 20).

        Returns:
            List of dicts with title, id, and pagerank score (0-1).
        """
        G, node_by_id = _load_graph_from_db()

        if len(G) == 0:
            return []

        # Compute PageRank
        scores = nx.pagerank(G)

        # Format results
        results = [
            {
                "title": node_by_id[node_id].get("title", "UNKNOWN"),
                "id": node_id,
                "score": float(scores[node_id]),
            }
            for node_id in sorted(scores, key=scores.get, reverse=True)[:limit]
            if node_id in node_by_id
        ]

        return results

    @mcp.tool()
    def org_roam_communities(
        resolution: float = 1.0,
    ) -> dict:
        """Detect communities/clusters using Louvain algorithm.

        Identifies natural topic clusters in your knowledge graph.
        Resolution controls granularity: <1 finds larger communities, >1 finds smaller.

        Args:
            resolution: Resolution parameter (0.5-2.0). Default 1.0 for balanced clustering.

        Returns:
            Dict with communities list and summary statistics.
        """
        G, node_by_id = _load_graph_from_db()

        if len(G) == 0:
            return {"communities": [], "num_communities": 0}

        try:
            import community as community_louvain

            # Convert to undirected for community detection
            G_undirected = G.to_undirected()

            # Find communities using Louvain algorithm
            partition_dict = community_louvain.best_partition(
                G_undirected,
                resolution=resolution,
            )

            # Group nodes by community
            communities = {}
            for node_id, community_id in partition_dict.items():
                if community_id not in communities:
                    communities[community_id] = []
                communities[community_id].append(
                    {
                        "title": node_by_id.get(node_id, {}).get("title", "UNKNOWN"),
                        "id": node_id,
                    }
                )

            # Calculate modularity
            modularity = community_louvain.modularity(
                partition_dict, G_undirected
            )

            return {
                "communities": communities,
                "num_communities": len(communities),
                "modularity": float(modularity),
            }

        except ImportError:
            return {
                "error": "python-louvain not installed. Install with: pip install python-louvain"
            }

    @mcp.tool()
    def org_roam_betweenness(limit: int = 20) -> list[dict]:
        """Find bridge nodes between clusters.

        Betweenness centrality identifies nodes that connect different parts
        of your knowledge graph. High scores indicate synthesis/integration points.

        Args:
            limit: Number of nodes to return (default 20).

        Returns:
            List of dicts with title, id, and betweenness score.
        """
        G, node_by_id = _load_graph_from_db()

        if len(G) == 0:
            return []

        # Compute betweenness centrality
        scores = nx.betweenness_centrality(G)

        # Format results
        results = [
            {
                "title": node_by_id[node_id].get("title", "UNKNOWN"),
                "id": node_id,
                "score": float(scores[node_id]),
            }
            for node_id in sorted(scores, key=scores.get, reverse=True)[:limit]
            if node_id in node_by_id
        ]

        return results

    @mcp.tool()
    def org_roam_closeness(limit: int = 20) -> list[dict]:
        """Compute closeness centrality (distance-based importance).

        Closeness measures how quickly a node can reach all others.
        High scores indicate central nodes in the graph structure.

        Args:
            limit: Number of nodes to return (default 20).

        Returns:
            List of dicts with title, id, and closeness score.
        """
        G, node_by_id = _load_graph_from_db()

        if len(G) == 0:
            return []

        # Compute closeness centrality
        scores = nx.closeness_centrality(G)

        # Format results
        results = [
            {
                "title": node_by_id[node_id].get("title", "UNKNOWN"),
                "id": node_id,
                "score": float(scores[node_id]),
            }
            for node_id in sorted(scores, key=scores.get, reverse=True)[:limit]
            if node_id in node_by_id
        ]

        return results

    @mcp.tool()
    def org_roam_clustering_coefficient(node_id: str = None) -> dict:
        """Measure local density and clustering.

        Clustering coefficient measures how clustered a node's neighbors are.
        High values indicate tight topic clusters; low values indicate bridge nodes.

        Args:
            node_id: Specific node to measure. If None, returns graph-wide average.

        Returns:
            Dict with clustering coefficient and interpretation.
        """
        G, node_by_id = _load_graph_from_db()

        if len(G) == 0:
            return {"error": "Graph is empty"}

        if node_id is not None:
            # Specific node
            if node_id not in G:
                return {"error": f"Node {node_id} not found"}

            coefficient = nx.clustering(G, node_id)
            title = node_by_id.get(node_id, {}).get("title", "UNKNOWN")

            return {
                "node_id": node_id,
                "title": title,
                "clustering_coefficient": float(coefficient),
                "interpretation": (
                    "High (>0.5): Node is in a tight cluster"
                    if coefficient > 0.5
                    else "Medium (0.2-0.5): Mixed connectivity"
                    if coefficient > 0.2
                    else "Low (<0.2): Node bridges different clusters"
                ),
            }
        else:
            # Graph-wide average
            avg_coefficient = nx.average_clustering(G)

            return {
                "average_clustering_coefficient": float(avg_coefficient),
                "interpretation": (
                    "High (>0.5): Graph has tight clusters"
                    if avg_coefficient > 0.5
                    else "Medium (0.2-0.5): Mixed structure"
                    if avg_coefficient > 0.2
                    else "Low (<0.2): Graph is sparse/decentralized"
                ),
            }

    @mcp.tool()
    def org_roam_graph_stats() -> dict:
        """Compute overall graph health metrics.

        Returns comprehensive statistics about your knowledge graph structure.

        Returns:
            Dict with node count, edge count, density, diameter, and other metrics.
        """
        G, node_by_id = _load_graph_from_db()

        if len(G) == 0:
            return {
                "error": "Graph is empty",
                "num_nodes": 0,
                "num_edges": 0,
            }

        num_nodes = G.number_of_nodes()
        num_edges = G.number_of_edges()
        density = nx.density(G)

        # Compute diameter and avg shortest path (for largest connected component)
        largest_cc = max(nx.weakly_connected_components(G), key=len)
        G_largest = G.subgraph(largest_cc).copy()

        diameter = None
        avg_shortest_path = None

        if len(G_largest) > 1:
            try:
                # For weakly connected graph (treating as undirected for diameter)
                G_undirected = G_largest.to_undirected()
                diameter = nx.diameter(G_undirected)
                lengths = nx.all_pairs_dijkstra_path_length(G_undirected)
                total_length = sum(
                    length for source, targets in lengths for length in targets.values()
                )
                avg_shortest_path = total_length / (len(G_undirected) ** 2)
            except (nx.NetworkXError, ZeroDivisionError):
                pass

        num_components = nx.number_weakly_connected_components(G)
        degree_dict = dict(G.degree())
        avg_degree = (
            sum(degree_dict.values()) / num_nodes if num_nodes > 0 else 0
        )

        return {
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "density": float(density),
            "num_components": num_components,
            "largest_component_size": len(G_largest),
            "avg_degree": float(avg_degree),
            "diameter": diameter,
            "avg_shortest_path": float(avg_shortest_path) if avg_shortest_path else None,
            "interpretation": {
                "density": (
                    f"Sparse graph ({density:.4f}). "
                    f"Most nodes only connected to small subset."
                ),
                "components": (
                    f"Graph has {num_components} connected component(s). "
                    f"Largest contains {len(G_largest)}/{num_nodes} nodes."
                ),
            },
        }

    @mcp.tool()
    def org_roam_suggest_links(
        node_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Suggest new links using common neighbor similarity.

        Identifies nodes that should be linked based on shared connections.
        Uses Jaccard similarity: nodes linked to by many of your neighbors.

        Args:
            node_id: Node to find link suggestions for.
            limit: Maximum suggestions to return (default 10).

        Returns:
            List of suggested (title, id, score) for unlinked nodes.
        """
        G, node_by_id = _load_graph_from_db()

        if node_id not in G:
            return []

        # Find all nodes with paths of length 2 (common neighbors)
        suggestions = {}

        for neighbor in G.successors(node_id):
            for potential_link in G.successors(neighbor):
                # Skip if already linked or same node
                if potential_link == node_id or G.has_edge(node_id, potential_link):
                    continue

                # Count common neighbors (Jaccard-like score)
                common_neighbors = len(
                    set(G.successors(node_id)) & set(G.successors(potential_link))
                )

                if potential_link not in suggestions:
                    suggestions[potential_link] = 0

                suggestions[potential_link] += common_neighbors

        # Sort by score
        sorted_suggestions = sorted(
            suggestions.items(), key=lambda x: x[1], reverse=True
        )[:limit]

        results = [
            {
                "title": node_by_id.get(sugg_id, {}).get("title", "UNKNOWN"),
                "id": sugg_id,
                "score": score,
                "reason": "shared connections via 2-hop neighbors",
            }
            for sugg_id, score in sorted_suggestions
            if sugg_id in node_by_id
        ]

        return results

    @mcp.tool()
    def org_roam_connected_components() -> dict:
        """Find disconnected subgraphs and isolated components.

        Identifies topic clusters that are not connected to the main graph.
        Useful for spotting isolated knowledge areas needing integration.

        Returns:
            Dict with component information and node assignments.
        """
        G, node_by_id = _load_graph_from_db()

        if len(G) == 0:
            return {"components": [], "num_components": 0}

        # Get weakly connected components (treating as undirected for connectivity)
        components = list(nx.weakly_connected_components(G))
        components = sorted(components, key=lambda c: len(c), reverse=True)

        result_components = []

        degree_dict = dict(G.degree())

        for i, component_nodes in enumerate(components):
            # Find largest hub in component
            hub_node = None
            max_degree = 0

            for node in component_nodes:
                degree = degree_dict.get(node, 0)
                if degree > max_degree:
                    max_degree = degree
                    hub_node = node

            component_info = {
                "component_id": i,
                "size": len(component_nodes),
                "hub_node": (
                    {
                        "title": node_by_id.get(hub_node, {}).get("title", "UNKNOWN"),
                        "id": hub_node,
                        "degree": max_degree,
                    }
                    if hub_node
                    else None
                ),
                "nodes": [
                    {
                        "title": node_by_id.get(node_id, {}).get("title", "UNKNOWN"),
                        "id": node_id,
                    }
                    for node_id in sorted(component_nodes)
                    if node_id in node_by_id
                ],
            }

            result_components.append(component_info)

        return {
            "num_components": len(components),
            "components": result_components,
            "interpretation": (
                f"Graph is fully connected (1 component)."
                if len(components) == 1
                else f"Graph has {len(components)} separate components. "
                f"Largest component has {components[0].__len__()} nodes. "
                f"Consider linking isolated areas."
            ),
        }
