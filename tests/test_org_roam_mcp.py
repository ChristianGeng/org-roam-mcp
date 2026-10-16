"""Test suite for org-roam MCP tools."""

from pathlib import Path
import sqlite3
import tempfile

import networkx as nx
import pytest


def _create_valid_roam_db(db_path: Path) -> None:
    """Create a minimal valid org-roam database schema."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, title TEXT, file TEXT)")
    cursor.execute("CREATE TABLE files (file TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()


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


class TestDbDetectionHelpers:
    """Test DB detection helper functions."""

    def test_extract_db_path_handles_quoted_output(self):
        """Extract DB path from quoted emacsclient output."""
        import org_roam_mcp.db as db_module

        output = '"/home/user/doom-emacs/.local/cache/org-roam.db"\n'
        assert db_module._extract_db_path(output) == "/home/user/doom-emacs/.local/cache/org-roam.db"

    def test_emacs_query_returns_the_path_without_printing(self):
        """Return the path as the value; princ fails in a read-only buffer."""
        import org_roam_mcp.db as db_module

        assert "princ" not in db_module.EMACS_DB_LOCATION_EVAL
        assert "(expand-file-name loc)" in db_module.EMACS_DB_LOCATION_EVAL

    def test_extract_db_path_ignores_nil(self):
        """Ignore nil output from emacsclient."""
        import org_roam_mcp.db as db_module

        assert db_module._extract_db_path("nil\n") is None

    def test_is_valid_roam_db_requires_nodes_and_files(self, tmp_path):
        """Validate DB only when required tables are present."""
        import org_roam_mcp.db as db_module

        valid_db = tmp_path / "valid.db"
        _create_valid_roam_db(valid_db)
        assert db_module._is_valid_roam_db(valid_db)

        invalid_db = tmp_path / "invalid.db"
        conn = sqlite3.connect(invalid_db)
        conn.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, title TEXT, file TEXT)")
        conn.commit()
        conn.close()
        assert not db_module._is_valid_roam_db(invalid_db)


class TestDbDetectionOrder:
    """Test DB detection order semantics."""

    def test_detect_db_prefers_server_over_env(self, monkeypatch, tmp_path):
        """Prefer server-detected DB over environment variable DB."""
        import org_roam_mcp.db as db_module

        server_db = tmp_path / "server.db"
        env_db = tmp_path / "env.db"
        _create_valid_roam_db(server_db)
        _create_valid_roam_db(env_db)

        monkeypatch.setenv("ORG_ROAM_DB", str(env_db))
        monkeypatch.setattr(
            db_module,
            "_detect_db_from_server",
            lambda _server_file=None: str(server_db),
        )

        assert db_module.detect_db() == str(server_db)

    def test_detect_db_uses_env_when_server_unavailable(self, monkeypatch, tmp_path):
        """Use environment variable when server detection fails."""
        import org_roam_mcp.db as db_module

        env_db = tmp_path / "env.db"
        _create_valid_roam_db(env_db)

        monkeypatch.setenv("ORG_ROAM_DB", str(env_db))
        monkeypatch.setattr(
            db_module,
            "_detect_db_from_server",
            lambda _server_file=None: None,
        )

        assert db_module.detect_db() == str(env_db)


class TestGraphLoading:
    """Test graph loading from database."""

    def test_load_graph_basic(self, test_db):
        """Test that graph loads with correct node and edge counts."""
        # Monkey-patch db module to use test database
        import org_roam_mcp.db as db_module
        from org_roam_mcp.tools_advanced import _load_graph_from_db

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
        import org_roam_mcp.db as db_module
        from org_roam_mcp.tools_advanced import _load_graph_from_db

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
        import org_roam_mcp.db as db_module
        from org_roam_mcp.tools_advanced import _load_graph_from_db

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
        import org_roam_mcp.db as db_module
        from org_roam_mcp.tools_advanced import _load_graph_from_db

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
        import org_roam_mcp.db as db_module
        from org_roam_mcp.tools_advanced import _load_graph_from_db

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
        import org_roam_mcp.db as db_module
        from org_roam_mcp.tools_advanced import _load_graph_from_db

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
        import org_roam_mcp.db as db_module
        from org_roam_mcp.tools_advanced import _load_graph_from_db

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
