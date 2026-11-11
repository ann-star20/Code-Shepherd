"""Opt-in against a DEDICATED Neo4j database; never uses the default URI."""

import os
import time
from uuid import uuid4

import pytest
from neo4j.exceptions import Neo4jError

from app.neo4j_client import close_driver
from app.video_models import SearchTarget
from app.video_store import Neo4jVideoStore

pytestmark = pytest.mark.skipif(
    not os.getenv("M5_TEST_NEO4J_URI"), reason="Dedicated Neo4j not configured"
)


@pytest.fixture
async def store(monkeypatch):
    await close_driver()
    monkeypatch.setenv("NEO4J_URI", os.environ["M5_TEST_NEO4J_URI"])
    monkeypatch.setenv("NEO4J_USER", os.getenv("M5_TEST_NEO4J_USER", "neo4j"))
    monkeypatch.setenv("NEO4J_PASSWORD", os.environ["M5_TEST_NEO4J_PASSWORD"])
    monkeypatch.setenv("NEO4J_DATABASE", os.getenv("M5_TEST_NEO4J_DATABASE", "neo4j"))
    value = Neo4jVideoStore()
    await value.initialize()
    yield value
    await close_driver()


async def test_atomic_pool_replacement_idempotency_expiry_and_rollback(store):
    now = int(time.time())
    suffix = uuid4().hex
    target = SearchTarget("__m5_test_" + suffix, "test query")
    token = "test_" + suffix
    video_id = "__m5_video_" + suffix
    await store._run("CREATE (:Concept {name:$name})", name=target.concept_name)
    assert await store.acquire(token, now)
    video = {
        "video_id": video_id,
        "title": "first",
        "url": "https://example.test",
        "thumbnail": None,
        "channel_title": None,
    }
    try:
        await store.replace_pool(
            target, [video, {**video, "title": "duplicate"}], now, token
        )
        await store.replace_pool(target, [video], now, token)
        assert [
            v["title"]
            for v in await store.fetch_candidates(target.concept_name, target.query)
        ] == ["first"]
        counts = await store._run(
            "MATCH (p:YouTubeSearchPool {key:$key})-[r:HAS_CANDIDATE]->() RETURN count(r) AS count",
            key=target.key,
        )
        assert counts[0]["count"] == 1
        with pytest.raises(Neo4jError):
            await store.replace_pool(target, [{**video, "video_id": None}], now, token)
        assert [
            v["title"]
            for v in await store.fetch_candidates(target.concept_name, target.query)
        ] == ["first"]
        await store.replace_pool(target, [], now, token)
        assert await store.fetch_candidates(target.concept_name, target.query) == []
        await store.replace_pool(target, [video], now, token)
        await store._run(
            "MATCH (p:YouTubeSearchPool {key:$key}) SET p.expires_at=0", key=target.key
        )
        assert await store.fetch_candidates(target.concept_name, target.query) == []
    finally:
        await store.release(token)
        await store._run(
            "MATCH (c:Concept {name:$name}) DETACH DELETE c", name=target.concept_name
        )
        await store._run(
            "MATCH (p:YouTubeSearchPool {key:$key}) DETACH DELETE p", key=target.key
        )
        await store._run(
            "MATCH (v:YouTubeVideo {video_id:$id}) DETACH DELETE v", id=video_id
        )
