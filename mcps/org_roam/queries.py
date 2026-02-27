"""SQL query templates for org-roam, ported from org-roam-graph-query.sh.

Note: org-roam stores all string values with Elisp-style embedded quotes,
e.g. the type "id" is stored as '"id"' in the database.
All link queries filter on type = '"id"' to traverse only node-to-node links
(excluding https, http, file, mailto links).
"""

# Links filter: only org-roam node-to-node links
_ID_TYPE = """l.type = '"id"'"""

FIND = """
SELECT id, title, file
FROM nodes
WHERE title LIKE '%' || ? || '%'
ORDER BY title
"""

BACKLINKS = f"""
SELECT n.title, n.id, n.file
FROM links l
JOIN nodes n ON n.id = l.source
WHERE l.dest = ?
  AND {_ID_TYPE}
ORDER BY n.title
"""

BFS = f"""
WITH RECURSIVE bfs(id, depth, path) AS (
    SELECT ?, 0, CAST(? AS TEXT)
    UNION ALL
    SELECT l.dest,
           bfs.depth + 1,
           bfs.path || ',' || l.dest
    FROM links l
    JOIN bfs ON l.source = bfs.id
    WHERE bfs.depth < ?
      AND bfs.path NOT LIKE '%' || l.dest || '%'
      AND {_ID_TYPE}
)
SELECT DISTINCT n.title, n.id, MIN(bfs.depth) AS hops
FROM bfs
JOIN nodes n ON n.id = bfs.id
WHERE bfs.id != ?
GROUP BY n.id
ORDER BY hops, n.title
"""

SHORTEST_PATH = f"""
WITH RECURSIVE ps(id, depth, path) AS (
    SELECT ?, 0, CAST(? AS TEXT)
    UNION ALL
    SELECT l.dest,
           ps.depth + 1,
           ps.path || ',' || l.dest
    FROM links l
    JOIN ps ON l.source = ps.id
    WHERE ps.depth < 8
      AND ps.path NOT LIKE '%' || l.dest || '%'
      AND {_ID_TYPE}
)
SELECT ps.path, ps.depth
FROM ps
WHERE ps.id = ?
ORDER BY ps.depth
LIMIT 3
"""

RESOLVE_TITLE = """
SELECT title FROM nodes WHERE id = ?
"""

COMMON_NEIGHBORS = f"""
SELECT n.title, n.id, COUNT(*) AS shared_links
FROM links l1
JOIN links l2 ON l1.dest = l2.dest
JOIN nodes n ON n.id = l2.source
WHERE l1.source = ?
  AND l2.source != ?
  AND l2.source != ?
  AND l1.type = '"id"'
  AND l2.type = '"id"'
GROUP BY n.id
ORDER BY shared_links DESC
LIMIT 15
"""

CENTRAL = f"""
SELECT n.title,
       n.id,
       COUNT(DISTINCT lo.dest) AS out_links,
       COUNT(DISTINCT li.source) AS in_links,
       COUNT(DISTINCT lo.dest) + COUNT(DISTINCT li.source) AS total
FROM nodes n
LEFT JOIN links lo ON lo.source = n.id AND lo.type = '"id"'
LEFT JOIN links li ON li.dest = n.id AND li.type = '"id"'
GROUP BY n.id
ORDER BY total DESC
LIMIT ?
"""

ORPHANS = f"""
SELECT n.title, n.id, n.file
FROM nodes n
WHERE n.id NOT IN (SELECT DISTINCT source FROM links WHERE type = '"id"')
  AND n.id NOT IN (SELECT DISTINCT dest FROM links WHERE type = '"id"')
ORDER BY n.title
"""

GET_ALL_NODES = """
SELECT id, title, file
FROM nodes
ORDER BY title
"""

GET_ALL_LINKS = f"""
SELECT source, dest, type
FROM links l
WHERE {_ID_TYPE}
"""
