// QUERY: ontology_layers
MATCH (d:Domain) RETURN 'L1 Domain' AS layer, count(d) AS total
UNION ALL
MATCH (c:Concept) RETURN 'L2 Concept' AS layer, count(c) AS total
UNION ALL
MATCH (m:Mechanism) RETURN 'L3 Mechanism' AS layer, count(m) AS total
UNION ALL
MATCH (e:CodeExample) RETURN 'L4 CodeExample' AS layer, count(e) AS total;

// QUERY: ontology_graph
MATCH path = (c:Concept)-[:BELONGS_TO|MITIGATED_BY|CAUSED_BY|AFFECTS|HAS_EXAMPLE*1..2]->()
RETURN path
LIMIT 300;

// QUERY: sql_injection_graph
MATCH (c:Concept {name: 'SQLi'})
OPTIONAL MATCH path = (c)-[:BELONGS_TO|MITIGATED_BY|CAUSED_BY|AFFECTS|HAS_EXAMPLE*1..2]->()
RETURN c, path
LIMIT 100;

// QUERY: youtube_graph
MATCH path = (c:Concept {name: 'SQLi'})-[:HAS_VIDEO_POOL]->(p:YouTubeSearchPool)-[:HAS_CANDIDATE]->(v:YouTubeVideo)
WHERE p.expires_at > timestamp() / 1000
  AND v.fetched_at > timestamp() / 1000 - 28 * 86400
RETURN path
LIMIT 150;

// QUERY: youtube_links_and_timestamps
MATCH (:Concept {name: 'SQLi'})-[:HAS_VIDEO_POOL]->(p:YouTubeSearchPool)-[r:HAS_CANDIDATE]->(v:YouTubeVideo)
WHERE p.expires_at > timestamp() / 1000
  AND v.fetched_at > timestamp() / 1000 - 28 * 86400
RETURN p.query AS search_query, r.position + 1 AS candidate_order,
       v.title AS title, v.url AS youtube_url,
       datetime({epochSeconds: v.created_at}) AS created_at,
       datetime({epochSeconds: v.updated_at}) AS updated_at,
       datetime({epochSeconds: v.fetched_at}) AS fetched_at,
       datetime({epochSeconds: p.expires_at}) AS pool_expires_at
ORDER BY search_query, candidate_order
LIMIT 50;

// QUERY: django_parameterized_query
MATCH (:Concept {name: 'SQLi'})-[:HAS_VIDEO_POOL]->(p:YouTubeSearchPool)-[r:HAS_CANDIDATE]->(v:YouTubeVideo)
WHERE p.query CONTAINS 'django' AND p.query CONTAINS 'parameterized query'
  AND p.expires_at > timestamp() / 1000
  AND v.fetched_at > timestamp() / 1000 - 28 * 86400
RETURN p.query AS search_query, v.title AS title, v.url AS youtube_url,
       r.position + 1 AS candidate_order
ORDER BY candidate_order
LIMIT 10;

// QUERY: pool_refresh_status
MATCH (c:Concept)-[:HAS_VIDEO_POOL]->(p:YouTubeSearchPool)
OPTIONAL MATCH (p)-[:HAS_CANDIDATE]->(v:YouTubeVideo)
RETURN c.name AS concept, p.query AS search_query,
       count(DISTINCT v) AS stored_videos,
       datetime({epochSeconds: p.created_at}) AS created_at,
       datetime({epochSeconds: p.updated_at}) AS updated_at,
       datetime({epochSeconds: p.fetched_at}) AS last_collected_at,
       datetime({epochSeconds: p.fetched_at + 7 * 86400}) AS refresh_eligible_at,
       datetime({epochSeconds: p.expires_at}) AS expires_at,
       CASE WHEN p.expires_at <= timestamp() / 1000 THEN 'EXPIRED'
            WHEN p.fetched_at <= timestamp() / 1000 - 7 * 86400 THEN 'DUE'
            ELSE 'FRESH' END AS refresh_status
ORDER BY concept, search_query;

// QUERY: collection_budget
MATCH (b:YouTubeSearchBudget)
RETURN b.day AS pacific_date, b.calls AS reserved_search_attempts,
       datetime({epochSeconds: b.created_at}) AS created_at
ORDER BY pacific_date DESC
LIMIT 7;
