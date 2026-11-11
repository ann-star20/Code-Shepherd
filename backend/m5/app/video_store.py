"""Neo4j persistence for M5 search pools and a shared collection budget."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from neo4j import AsyncManagedTransaction

from app.graph_query import ConceptGraphResponse, fetch_concept, fetch_overview
from app.neo4j_client import get_database, get_driver
from app.video_models import RETENTION_SECONDS, SearchTarget, VideoCandidate


class LeaseLostError(RuntimeError):
    pass


class Neo4jVideoStore:
    async def _run(self, query: str, **params: object) -> list[dict]:
        async with get_driver().session(database=get_database()) as session:
            result = await session.run(query, **params)
            return await result.data()

    async def initialize(self) -> None:
        for label, field in [
            ("YouTubeVideo", "video_id"),
            ("YouTubeSearchPool", "key"),
            ("YouTubeCollectionControl", "name"),
            ("YouTubeSearchBudget", "day"),
        ]:
            # Identifiers come exclusively from the static allowlist above.
            await self._run(
                f"CREATE CONSTRAINT m5_{label}_{field} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{field} IS UNIQUE"
            )

    async def acquire(self, token: str, now: int) -> bool:
        rows = await self._run(
            """
        MERGE (lock:YouTubeCollectionControl {name:'collector'})
        SET lock.revision = coalesce(lock.revision, 0) + 1
        WITH lock WHERE coalesce(lock.expires_at, 0) <= $now
        SET lock.owner=$token, lock.expires_at=$now + 120
        RETURN lock.owner AS owner
        """,
            token=token,
            now=now,
        )
        return bool(rows)

    async def release(self, token: str) -> None:
        await self._run(
            """
        MATCH (lock:YouTubeCollectionControl {name:'collector'})
        SET lock.revision = coalesce(lock.revision, 0) + 1
        WITH lock WHERE lock.owner=$token
        SET lock.owner='', lock.expires_at=0
        """,
            token=token,
        )

    async def cleanup(self, now: int) -> None:
        await self._run(
            """
        MATCH (pool:YouTubeSearchPool)
        WHERE coalesce(pool.fetched_at, 0) <= $cutoff OR NOT EXISTS {
          MATCH (:Concept)-[:HAS_VIDEO_POOL]->(pool)
        }
        DETACH DELETE pool
        """,
            cutoff=now - RETENTION_SECONDS,
        )
        await self._run(
            """
        MATCH (video:YouTubeVideo)
        WHERE coalesce(video.fetched_at, 0) <= $cutoff OR NOT EXISTS {
          MATCH (:YouTubeSearchPool)-[:HAS_CANDIDATE]->(video)
        }
        DETACH DELETE video
        """,
            cutoff=now - RETENTION_SECONDS,
        )
        await self._run(
            "MATCH (b:YouTubeSearchBudget) WHERE b.created_at < $cutoff DELETE b",
            cutoff=now - 35 * 86400,
        )

    async def list_concepts(self) -> list[ConceptGraphResponse]:
        overview = await fetch_overview()
        concepts = []
        for entry in overview.concepts:
            concept = await fetch_concept(entry.concept_name)
            if concept is not None:
                concepts.append(concept)
        return concepts

    async def pool_times(self) -> dict[str, int]:
        rows = await self._run(
            "MATCH (p:YouTubeSearchPool) RETURN p.key AS key, p.fetched_at AS fetched_at"
        )
        return {row["key"]: row["fetched_at"] or 0 for row in rows}

    async def reserve_search(self, token: str, now: int, daily_limit: int) -> bool:
        day = (
            datetime.fromtimestamp(now, ZoneInfo("America/Los_Angeles"))
            .date()
            .isoformat()
        )
        rows = await self._run(
            """
        MATCH (lock:YouTubeCollectionControl {name:'collector'})
        SET lock.revision = coalesce(lock.revision, 0) + 1
        WITH lock WHERE lock.owner=$token AND lock.expires_at > $now
        SET lock.expires_at=$now + 120
        MERGE (budget:YouTubeSearchBudget {day:$day})
        ON CREATE SET budget.calls=0, budget.created_at=$now
        SET budget.revision=coalesce(budget.revision, 0) + 1
        WITH budget WHERE budget.calls < $daily_limit
        SET budget.calls=budget.calls + 1
        RETURN budget.calls AS calls
        """,
            token=token,
            now=now,
            day=day,
            daily_limit=daily_limit,
        )
        return bool(rows)

    async def renew(self, token: str, now: int) -> bool:
        rows = await self._run(
            """
        MATCH (lock:YouTubeCollectionControl {name:'collector'})
        SET lock.revision=coalesce(lock.revision, 0) + 1
        WITH lock WHERE lock.owner=$token AND lock.expires_at > $now
        SET lock.expires_at=$now + 120 RETURN lock.owner AS owner
        """,
            token=token,
            now=now,
        )
        return bool(rows)

    async def videos_due(self, now: int) -> list[str]:
        rows = await self._run(
            """
        MATCH (v:YouTubeVideo) WHERE v.fetched_at <= $cutoff
        RETURN v.video_id AS video_id ORDER BY v.fetched_at LIMIT 50
        """,
            cutoff=now - 86400,
        )
        return [row["video_id"] for row in rows]

    async def refresh_videos(
        self, ids: list[str], videos: list[VideoCandidate], now: int, token: str
    ) -> None:
        valid = [video for video in videos if video["video_id"] in ids]

        async def refresh(tx: AsyncManagedTransaction) -> None:
            guard = await tx.run(
                """
            MATCH (lock:YouTubeCollectionControl {name:'collector'})
            SET lock.revision=coalesce(lock.revision, 0) + 1
            WITH lock WHERE lock.owner=$token AND lock.expires_at > $now
            RETURN lock.owner AS owner
            """,
                token=token,
                now=now,
            )
            if await guard.single() is None:
                raise LeaseLostError("Collector lease expired")
            result = await tx.run(
                """
            MATCH (v:YouTubeVideo) WHERE v.video_id IN $ids AND NOT v.video_id IN $visible
            DETACH DELETE v
            """,
                ids=ids,
                visible=[video["video_id"] for video in valid],
            )
            await result.consume()
            result = await tx.run(
                """
            UNWIND $videos AS item
            MATCH (v:YouTubeVideo {video_id:item.video_id})
            SET v.title=item.title, v.url=item.url, v.thumbnail=item.thumbnail,
                v.channel_title=item.channel_title, v.fetched_at=$now, v.updated_at=$now
            """,
                videos=valid,
                now=now,
            )
            await result.consume()

        async with get_driver().session(database=get_database()) as session:
            await session.execute_write(refresh)

    async def replace_pool(
        self, target: SearchTarget, videos: list[VideoCandidate], now: int, token: str
    ) -> None:
        # A transaction publishes a complete result set, including a successful empty set.
        # video_id uniqueness is also enforced by a database constraint.
        unique: dict[str, VideoCandidate] = {}
        for video in videos:
            unique.setdefault(video["video_id"], video)
        rows = [{**video, "position": idx} for idx, video in enumerate(unique.values())]

        async def replace(tx: AsyncManagedTransaction) -> None:
            guard = await tx.run(
                """
            MATCH (lock:YouTubeCollectionControl {name:'collector'})
            SET lock.revision=coalesce(lock.revision, 0) + 1
            WITH lock WHERE lock.owner=$token AND lock.expires_at > $now
            MATCH (c:Concept) WHERE toLower(c.name)=toLower($concept)
            MERGE (p:YouTubeSearchPool {key:$key})
            ON CREATE SET p.created_at=$now
            SET p.query=$search_query, p.fetched_at=$now, p.expires_at=$expires,
                p.updated_at=$now
            MERGE (c)-[:HAS_VIDEO_POOL]->(p)
            RETURN p.key AS key
            """,
                token=token,
                now=now,
                concept=target.concept_name,
                key=target.key,
                search_query=target.query,
                expires=now + RETENTION_SECONDS,
            )
            if await guard.single() is None:
                raise LeaseLostError("Collector lease expired or concept was removed")
            result = await tx.run(
                "MATCH (:YouTubeSearchPool {key:$key})-[r:HAS_CANDIDATE]->() DELETE r",
                key=target.key,
            )
            await result.consume()
            result = await tx.run(
                """
            MATCH (p:YouTubeSearchPool {key:$key})
            UNWIND $videos AS item
            MERGE (v:YouTubeVideo {video_id:item.video_id})
            ON CREATE SET v.created_at=$now
            SET v.title=item.title, v.url=item.url, v.thumbnail=item.thumbnail,
                v.channel_title=item.channel_title, v.fetched_at=$now, v.updated_at=$now
            MERGE (p)-[r:HAS_CANDIDATE]->(v)
            SET r.position=item.position
            """,
                key=target.key,
                videos=rows,
                now=now,
            )
            await result.consume()

        async with get_driver().session(database=get_database()) as session:
            await session.execute_write(replace)

    async def fetch_candidates(
        self, concept_name: str, query: str
    ) -> list[VideoCandidate]:
        now = int(time.time())
        return await self._run(
            """
        MATCH (c:Concept)-[:HAS_VIDEO_POOL]->(p:YouTubeSearchPool {key:$key})
        WHERE toLower(c.name)=toLower($concept) AND p.expires_at > $now
        MATCH (p)-[r:HAS_CANDIDATE]->(v:YouTubeVideo)
        WHERE v.fetched_at > $cutoff
        RETURN v.video_id AS video_id, v.title AS title, v.url AS url,
               v.thumbnail AS thumbnail, v.channel_title AS channel_title
        ORDER BY r.position LIMIT 50
        """,
            key=SearchTarget(concept_name, query).key,
            concept=concept_name,
            now=now,
            cutoff=now - RETENTION_SECONDS,
        )


async def fetch_candidates(concept_name: str, query: str) -> list[VideoCandidate]:
    from app import mock_data

    if mock_data.enabled():
        return mock_data.candidates(concept_name, query)
    return await Neo4jVideoStore().fetch_candidates(concept_name, query)
