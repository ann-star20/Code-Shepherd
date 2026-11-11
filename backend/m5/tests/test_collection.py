"""Collection lifecycle tests use an in-memory persistence boundary, no services."""

from unittest.mock import AsyncMock

import httpx

from app import video_collection
from app.graph_query import CodeExampleMeta, ConceptGraphResponse, MechanismMeta


class MemoryStore:
    def __init__(self):
        self.pools = {}
        self.concepts = [
            ConceptGraphResponse(
                concept_name="SQL_Injection",
                mechanisms=[
                    MechanismMeta(
                        mechanism_name="ParameterizedQuery",
                        code_examples=[
                            CodeExampleMeta(
                                unq_id="a", lang="Python", framework="Django"
                            )
                        ],
                    )
                ],
            )
        ]
        self.calls = 0
        self.released = False

    async def initialize(self):
        pass

    async def cleanup(self, now):
        pass

    async def acquire(self, token, now):
        return True

    async def release(self, token):
        self.released = True

    async def list_concepts(self):
        return self.concepts

    async def pool_times(self):
        return {k: v[0] for k, v in self.pools.items()}

    async def reserve_search(self, token, now, daily_limit):
        if self.calls >= daily_limit:
            return False
        self.calls += 1
        return True

    async def replace_pool(self, target, videos, now, token):
        self.pools[target.key] = (now, videos)


async def test_budget_limits_calls_and_rerun_skips_fresh_pools():
    collect = video_collection.collect
    store = MemoryStore()

    async def search(query):
        return [
            {
                "video_id": "v1",
                "title": "lesson",
                "url": "https://www.youtube.com/watch?v=v1",
            }
        ]

    first = await collect(store, search, now=1000000, max_searches=2, daily_limit=3)
    assert first["searches"] == 2
    assert len(store.pools) == 2
    assert store.released
    second = await collect(store, search, now=1000001, max_searches=10, daily_limit=3)
    assert second["searches"] == 1
    assert len(store.pools) == 3
    assert store.calls == 3


async def test_failed_search_preserves_previous_snapshot_and_timestamp():
    module = video_collection
    store = MemoryStore()
    target = module.build_targets(store.concepts)[0]
    store.pools[target.key] = (1, [{"video_id": "old"}])
    store.concepts = [ConceptGraphResponse(concept_name="SQL_Injection")]

    async def failed(query):
        raise httpx.ReadTimeout("secret URL")

    result = await module.collect(store, failed, now=1000000, max_searches=1)
    assert result["failed"] == 1
    assert store.pools[target.key] == (1, [{"video_id": "old"}])
    assert store.released


async def test_quota_error_stops_batch_without_replacing_any_pool():
    module = video_collection
    store = MemoryStore()

    async def denied(query):
        raise httpx.HTTPStatusError(
            "secret",
            request=httpx.Request("GET", "https://example.test"),
            response=httpx.Response(
                403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}}
            ),
        )

    result = await module.collect(store, denied, now=1000000)
    assert result["searches"] == 1
    assert result["status"] == "youtube_unavailable"
    assert store.pools == {}


async def test_empty_success_replaces_old_results_and_dry_run_never_searches():
    module = video_collection
    store = MemoryStore()
    search = AsyncMock(return_value=[])
    result = await module.collect(store, search, now=1000000, dry_run=True)
    assert result["pending"] > 5
    assert store.calls == 0
    assert store.pools == {}
    result = await module.collect(store, search, now=1000000, max_searches=1)
    assert list(store.pools.values()) == [(1000000, [])]
    assert result["updated"] == 1


async def test_context_queries_are_deduplicated_and_include_code_metadata():
    module = video_collection
    targets = module.build_targets(MemoryStore().concepts)
    assert len({t.key for t in targets}) == len(targets)
    assert any("Django" in t.query for t in targets)
    assert any("ParameterizedQuery" in t.query for t in targets)


async def test_busy_collector_does_not_consume_quota():
    module = video_collection
    store = MemoryStore()
    store.acquire = AsyncMock(return_value=False)
    result = await module.collect(store, AsyncMock(), now=1000000)
    assert result["status"] == "busy"
    assert store.calls == 0


async def test_lease_loss_stops_collection_without_publishing():
    module = video_collection
    store = MemoryStore()
    store.reserve_search = AsyncMock(return_value=False)
    result = await module.collect(store, AsyncMock(), now=1000000)
    assert result["status"] == "budget_or_lease_exhausted"
    assert not store.pools


async def test_daily_metadata_refresh_removes_unavailable_videos_without_search():
    module = video_collection
    store = MemoryStore()
    pending = [["visible", "deleted"]]

    async def due(now):
        return pending.pop(0) if pending else []

    store.videos_due = due
    store.renew = AsyncMock(return_value=True)
    stored = {"visible": {"title": "old"}, "deleted": {"title": "deleted"}}

    async def update(ids, videos, now, token):
        for vid in ids:
            stored.pop(vid, None)
        stored.update({v["video_id"]: v for v in videos})

    store.refresh_videos = update

    async def inspect(ids):
        assert ids == ["visible", "deleted"]
        return [{"video_id": "visible", "title": "new"}]

    async def search(query):
        return []

    result = await module.collect(
        store, search, now=1000000, max_searches=1, inspect_videos=inspect
    )
    assert stored == {"visible": {"video_id": "visible", "title": "new"}}
    assert result["metadata_updated"] == 1
