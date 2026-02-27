# Org-Roam MCP Usage Examples

Examples of how to use the org-roam MCP server tools in Claude Code sessions.

## Basic Operations

### Find notes by title

```
You: "Find my notes about machine learning"

Claude uses: org_roam_find("machine learning")

Returns:
  - Machine Learning Foundations (a-uuid-001)
  - Deep Learning (a-uuid-002)
  - Reinforcement Learning (a-uuid-003)
```

### Explore a node's neighborhood

```
You: "Show me the neighborhood around 'Transformer Architectures'"

Claude uses: org_roam_bfs("a-uuid-transformer", depth=2)

Returns:
  - Attention Mechanisms (depth 1)
  - Self-Attention (depth 1)
  - Multi-Head Attention (depth 1)
  - Positional Encoding (depth 2)
  - Scaling Laws (depth 2)
```

### See what links to a node

```
You: "What nodes reference 'GPT Architecture'?"

Claude uses: org_roam_backlinks("a-uuid-gpt")

Returns:
  - Language Models Hub
  - Prompt Engineering
  - Fine-Tuning Techniques
```

### Find the shortest path between concepts

```
You: "How is Machine Learning connected to Audio Processing?"

Claude uses: org_roam_shortest_path("a-uuid-ml", "a-uuid-audio")

Returns:
  - Path 1: ML → Deep Learning → Audio ML (3 hops)
  - Path 2: ML → Neural Nets → Signal Processing → Audio (4 hops)
```

## Graph Analysis

### Find your most important nodes

```
You: "What are the most central nodes in my knowledge graph?"

Claude uses: org_roam_pagerank(limit=10)

Returns (ranked by importance):
  1. Research Hub (score: 0.042)
  2. Machine Learning (score: 0.038)
  3. Audio Language Models (score: 0.035)
  4. Real-Time Systems (score: 0.032)
  5. Infrastructure (score: 0.029)
  ...
```

**Interpretation:** PageRank shows nodes that are influential due to
quality incoming links.
Higher-ranked nodes are well-connected synthesis points.

### Discover natural topic clusters

```
You: "Show me the main topic clusters in my graph"

Claude uses: org_roam_communities(resolution=1.0)

Returns:
  Community 1 (23 nodes):
    - Machine Learning Hub
    - Deep Learning
    - Neural Networks
    - Transformers
    - GPT Models

  Community 2 (18 nodes):
    - Audio Processing
    - Signal Processing
    - Real-Time Systems
    - Infrastructure
    - Performance Optimization

  Community 3 (12 nodes):
    - Audio Language Models
    - Voice Synthesis
    - Speech Recognition
    ...

Modularity: 0.61 (good clustering)
```

**Use case:** Validate your graph organization.
If clusters don't match your intended structure,
consider reorganizing links.

### Find bridge nodes between clusters

```
You: "Which nodes act as bridges between different topics?"

Claude uses: org_roam_betweenness(limit=10)

Returns:
  1. Knowledge Graph Design (score: 0.24)
  2. System Architecture (score: 0.19)
  3. Research Methodology (score: 0.16)
  4. Engineering Principles (score: 0.14)
  5. Data Structures (score: 0.12)
  ...
```

**Interpretation:** High betweenness scores indicate synthesis points.
These are nodes that connect disparate topic clusters.
Excellent candidates for deeper exploration and expansion.

### Measure graph centrality

```
You: "Which nodes are most 'central' to my graph?"

Claude uses: org_roam_closeness(limit=10)

Returns (ranked by closeness):
  1. Research Hub (score: 0.68)
  2. ML Hub (score: 0.65)
  3. Systems Architecture (score: 0.61)
  4. Design Patterns (score: 0.59)
  5. Theory Foundations (score: 0.57)
  ...
```

**Difference from PageRank:** Closeness measures how quickly
a node can reach all others (distance-based),
while PageRank measures quality of incoming links.

### Analyze clustering and topic coherence

```
You: "Is the 'Machine Learning' cluster tight or spread out?"

Claude uses: org_roam_clustering_coefficient(node_id="a-uuid-ml")

Returns:
  Node: Machine Learning Hub
  Clustering Coefficient: 0.68
  Interpretation: High (>0.5) - Node is in a tight cluster

This means:
  - The neighbors of this node are well-connected
  - It's in a cohesive topic area
  - Good candidate for topic leadership/hub
```

```
You: "Which nodes are bridges between clusters?"

Claude uses: org_roam_clustering_coefficient(node_id="a-uuid-bridge")

Returns:
  Node: System Architecture
  Clustering Coefficient: 0.12
  Interpretation: Low (<0.2) - Node bridges different clusters

This means:
  - Neighbors of this node are not well-connected
  - It connects disparate topic areas
  - Good candidate for cross-domain synthesis
```

### Get overall graph health metrics

```
You: "How healthy is my knowledge graph?"

Claude uses: org_roam_graph_stats()

Returns:
  Nodes: 205
  Edges: 452
  Density: 0.0107 (sparse - typical for large graphs)
  Diameter: 12 (longest shortest-path)
  Avg Shortest Path: 3.2
  Avg Degree: 2.2
  Components: 2 (1 main + 1 orphaned)
  Largest Component: 200 nodes (97.6%)

Interpretation:
  Graph is sparse but well-connected.
  Most nodes reach each other in 3 hops.
  One isolated component of ~5 nodes needs integration.
```

### Suggest missing links

```
You: "What nodes should 'Transformers' link to?"

Claude uses: org_roam_suggest_links("a-uuid-transformers", limit=10)

Returns:
  1. Attention Mechanisms (score: 8 - shared connections via MLPs)
  2. Self-Attention (score: 6 - shared via Attention)
  3. Neural Architecture (score: 4 - shared via Deep Learning)
  4. Scaling Laws (score: 3 - shared via LLMs)
  ...

Use case: Add links to strengthen graph connectivity
and make implicit relationships explicit.
```

### Find isolated subgraphs

```
You: "Are there any disconnected topic areas in my graph?"

Claude uses: org_roam_connected_components()

Returns:
  Component 1 (size: 200, hub: "Research Hub")
    - Main knowledge graph
    - Well-connected

  Component 2 (size: 3, hub: "Deprecated Notes")
    - Isolated subgraph
    - Should be linked or archived

  Component 3 (size: 2, hub: "TODO Items")
    - Very small isolated component
    - Needs integration or removal

Action: Link Component 2 and 3 nodes to main graph,
or archive them if obsolete.
```

## Advanced Workflows

### Validate graph organization

```
You: "Validate my knowledge graph structure"

Claude workflow:
  1. org_roam_graph_stats()        → Check overall health
  2. org_roam_communities()        → Verify expected clusters exist
  3. org_roam_connected_components() → Check for orphaned areas
  4. org_roam_orphans()            → Find isolated nodes

Summary:
  ✅ 205 nodes, 452 links (healthy density)
  ✅ 8 communities match intended structure
  ⚠️ 5 nodes in isolated component (needs linking)
  ⚠️ 3 orphaned nodes (verify: keep, link, or delete?)
```

### Plan graph expansion

```
You: "Where should I focus on adding new content?"

Claude workflow:
  1. org_roam_graph_stats()  → Identify sparse areas
  2. org_roam_suggest_links() → Find gap areas
  3. org_roam_betweenness()  → Find integration points

Recommendations:
  - Audio-ML is a bridge between two clusters
    (opportunity for synthesis content)
  - Real-Time Systems cluster is sparse
    (opportunity for deeper exploration)
  - Signal Processing lacks connections
    (consider adding 3-5 new nodes here)
```

### Discover synthesis opportunities

```
You: "Which topics would benefit from synthesis nodes?"

Claude workflow:
  1. org_roam_betweenness()     → Find bridge nodes
  2. org_roam_common_neighbors() → Find implicit connections
  3. org_roam_shortest_path()    → Understand connection paths

Results:
  - Machine Learning ↔ Audio Processing
    (synthesis topic: Audio ML)
  - Systems ↔ Theory
    (synthesis topic: Systems Design Patterns)
  - Infrastructure ↔ ML
    (synthesis topic: MLOps, Model Serving)
```

## Tips and Tricks

### Adjust clustering granularity

```
You: "Find finer-grained clusters"

Claude uses: org_roam_communities(resolution=1.5)
# Higher resolution → more, smaller communities

vs. org_roam_communities(resolution=0.8)
# Lower resolution → fewer, larger communities
```

### Filter results by relevance

```
You: "Find top 5 most important nodes"

Claude uses: org_roam_pagerank(limit=5)

vs. org_roam_central(limit=5)
# degree centrality (number of connections)

vs. org_roam_closeness(limit=5)
# distance-based centrality (quick reach)
```

### Understand different centrality measures

| Measure | Meaning | Use When |
|---------|---------|----------|
| **PageRank** | Quality of incoming links | Finding influential nodes |
| **Betweenness** | Bridges between clusters | Finding synthesis points |
| **Closeness** | Average distance to all | Finding central hubs |
| **Degree** | Number of direct connections | Finding popular nodes |

### Iterative refinement

```
You: "Improve my graph structure"

Session 1:
  1. org_roam_graph_stats()  → Baseline metrics
  2. org_roam_orphans()      → 8 orphaned nodes
  → Create 2 new hub nodes for these

Session 2:
  1. org_roam_graph_stats()  → Check improvement
  2. org_roam_communities()  → Verify clustering
  3. org_roam_suggest_links() → Add missing connections

Session 3:
  1. org_roam_graph_stats()  → Final verification
  → Density improved, components consolidated
```
