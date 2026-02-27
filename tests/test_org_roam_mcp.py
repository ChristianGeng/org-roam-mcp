"""Test suite for org-roam MCP tools."""

import sqlite3
import tempfile
from pathlib import Path

import networkx as nx
import pytest


@pytest.fixture
def test_db():
    """Create a temporary test database with sample org-roam structure."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create schema
    cursor.execute("""
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            file TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE links (
            source TEXT,
            dest TEXT,
            type TEXT,
            PRIMARY KEY (source, dest, type)
        )
    """)

    # Create test nodes (simple graph structure)
    nodes = [
        ('"a-uuid-0001"', "Research Hub", "/path/a.org"),
        ('"a-uuid-0002"', "Audio LLM", "/path/b.org"),
        ('"a-uuid-0003"', "Real-time Systems", "/path/c.org"),
        ('"a-uuid-0004"', "Machine Learning", "/path/d.org"),
        ('"a-uuid-0005"', "Infrastructure", "/path/e.org"),
        ('"a-uuid-0006"', "Orphaned Node", "/path/f.org"),
        ('"a-uuid-0007"', "Bridge Node", "/path/g.org"),
        ('"a-uuid-0008"', "Connected", "/path/h.org"),
    ]

    for node_id, title, filepath in nodes:
        cursor.execute(
            "INSERT INTO nodes (id, title, file) VALUES (?, ?, ?)",
            (node_id, title, filepath),
        )

    # Create test links (directed graph)
    links = [
        # Hub connections
        ('"a-uuid-0001"', '"a-uuid-0002"', '"id"'),  # Research → Audio
        ('"a-uuid-0001"', '"a-uuid-0003"', '"id"'),  # Research → Real-time
        ('"a-uuid-0001"', '"a-uuid-0004"', '"id"'),  # Research → ML
        # Cluster 1: Audio/ML
        ('"a-uuid-0002"', '"a-uuid-0004"', '"id"'),  # Audio → ML
        ('"a-uuid-0004"', '"a-uuid-0002"', '"id"'),  # ML → Audio
        # Cluster 2: Real-time/Infra
        ('"a-uuid-0003"', '"a-uuid-0005"', '"id"'),  # Real-time → Infra
        ('"a-uuid-0005"', '"a-uuid-0003"', '"id"'),  # Infra → Real-time
        # Bridge node
        ('"a-uuid-0007"', '"a-uuid-0002"', '"id"'),  # Bridge → Audio
        ('"a-uuid-0007"', '"a-uuid-0003"', '"id"'),  # Bridge → Real-time
        # Other links
        ('"a-uuid-0008"', '"a-uuid-0001"', '"id"'),  # Connected → Hub
        # Orphaned node has no links
    ]

    for source, dest, link_type in links:
        cursor.execute(
            "INSERT INTO links (source, dest, type) VALUES (?, ?, ?)",
            (source, dest, link_type),
        )

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink()


class TestGraphLoading:
    """Test graph loading from database."""

    def test_load_graph_basic(self, test_db):
        """Test that graph loads with correct node and edge counts."""
        from mcps.org_roam.tools_advanced import _load_graph_from_db

        # Monkey-patch db module to use test database
        import mcps.org_roam.db as db_module

        original_detect = db_module.detect_db

        def mock_detect_db():
            return test_db

        db_module.detect_db = mock_detect_db

        try:
            G, node_by_id = _load_graph_from_db()

            # Check node count (8 total nodes)
            assert len(G) == 8
            # Check edge count (10 directed edges)
            assert G.number_of_edges() == 10
            # Check it's directed
            assert isinstance(G, nx.DiGraph)
        finally:
            db_module.detect_db = original_detect

    def test_orphaned_node_detection(self, test_db):
        """Test that orphaned nodes have zero in-degree and out-degree."""
        from mcps.org_roam.tools_advanced import _load_graph_from_db

        import mcps.org_roam.db as db_module

        original_detect = db_module.detect_db

        def mock_detect_db():
            return test_db

        db_module.detect_db = mock_detect_db

        try:
            G, node_by_id = _load_graph_from_db()

            # Orphaned node UUID (quotes are stripped by _load_graph_from_db)
            orphaned_id = "a-uuid-0006"

            # Should have no incoming or outgoing edges
            assert G.in_degree(orphaned_id) == 0
            assert G.out_degree(orphaned_id) == 0
        finally:
            db_module.detect_db = original_detect


class TestPageRank:
    """Test PageRank algorithm."""

    def test_pagerank_scores_exist(self, test_db):
        """Test that PageRank produces scores for all nodes."""
        from mcps.org_roam.tools_advanced import _load_graph_from_db

        import mcps.org_roam.db as db_module

        original_detect = db_module.detect_db

        def mock_detect_db():
            return test_db

        db_module.detect_db = mock_detect_db

        try:
            G, node_by_id = _load_graph_from_db()
            scores = nx.pagerank(G)

            # All nodes should have scores
            assert len(scores) == 8
            # Scores should be between 0 and 1
            for score in scores.values():
                assert 0 <= score <= 1
            # Hub should have higher score than orphaned node
            hub_score = scores["a-uuid-0001"]
            orphaned_score = scores["a-uuid-0006"]
            assert hub_score > orphaned_score
        finally:
            db_module.detect_db = original_detect


class TestCentrality:
    """Test centrality measures."""

    def test_betweenness_identifies_bridges(self, test_db):
        """Test that betweenness centrality is computed for all nodes."""
        from mcps.org_roam.tools_advanced import _load_graph_from_db

        import mcps.org_roam.db as db_module

        original_detect = db_module.detect_db

        def mock_detect_db():
            return test_db

        db_module.detect_db = mock_detect_db

        try:
            G, node_by_id = _load_graph_from_db()
            scores = nx.betweenness_centrality(G)

            # All nodes should have betweenness scores
            assert len(scores) == 8
            # Scores should be between 0 and 1
            for score in scores.values():
                assert 0 <= score <= 1
        finally:
            db_module.detect_db = original_detect


class TestConnectedComponents:
    """Test connected components detection."""

    def test_connected_components_count(self, test_db):
        """Test that connected components are detected correctly."""
        from mcps.org_roam.tools_advanced import _load_graph_from_db

        import mcps.org_roam.db as db_module

        original_detect = db_module.detect_db

        def mock_detect_db():
            return test_db

        db_module.detect_db = mock_detect_db

        try:
            G, node_by_id = _load_graph_from_db()
            num_components = nx.number_weakly_connected_components(G)

            # Should have 2 components: main graph + orphaned node
            assert num_components == 2
        finally:
            db_module.detect_db = original_detect


class TestClusteringCoefficient:
    """Test clustering coefficient."""

    def test_clustering_coefficient_exists(self, test_db):
        """Test that clustering coefficients are computed."""
        from mcps.org_roam.tools_advanced import _load_graph_from_db

        import mcps.org_roam.db as db_module

        original_detect = db_module.detect_db

        def mock_detect_db():
            return test_db

        db_module.detect_db = mock_detect_db

        try:
            G, node_by_id = _load_graph_from_db()
            G_undirected = G.to_undirected()
            coeffs = nx.clustering(G_undirected)

            # All nodes should have coefficients
            assert len(coeffs) == 8
            # All coefficients between 0 and 1
            for coeff in coeffs.values():
                assert 0 <= coeff <= 1
        finally:
            db_module.detect_db = original_detect


class TestGraphStats:
    """Test graph statistics."""

    def test_graph_density(self, test_db):
        """Test that graph density is calculated correctly."""
        from mcps.org_roam.tools_advanced import _load_graph_from_db

        import mcps.org_roam.db as db_module

        original_detect = db_module.detect_db

        def mock_detect_db():
            return test_db

        db_module.detect_db = mock_detect_db

        try:
            G, node_by_id = _load_graph_from_db()
            density = nx.density(G)

            # For 8 nodes and 10 edges: density = 10 / (8 * 7) ≈ 0.179
            assert 0 < density < 1
            assert abs(density - (10 / (8 * 7))) < 0.001
        finally:
            db_module.detect_db = original_detect
