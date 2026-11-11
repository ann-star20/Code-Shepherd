"""Bounded background collection; serving never invokes this workflow."""

import time
from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import uuid4

import httpx
import structlog

from app.graph_query import ConceptGraphResponse
from app.keyword_builder import build_queries
from app.video_models import SearchTarget, VideoCandidate

log = structlog.get_logger()


class CollectionStore(Protocol):
    async def initialize(self) -> None: ...
    async def cleanup(self, now: int) -> None: ...
    async def acquire(self, token: str, now: int) -> bool: ...
    async def release(self, token: str) -> None: ...
    async def list_concepts(self) -> list[ConceptGraphResponse]: ...
    async def pool_times(self) -> dict[str, int]: ...
    async def reserve_search(self, token: str, now: int, daily_limit: int) -> bool: ...
    async def renew(self, token: str, now: int) -> bool: ...
    async def videos_due(self, now: int) -> list[str]: ...
    async def refresh_videos(
        self, ids: list[str], videos: list[VideoCandidate], now: int, token: str
    ) -> None: ...
    async def replace_pool(
        self, target: SearchTarget, videos: list[VideoCandidate], now: int, token: str
    ) -> None: ...


def build_targets(concepts: list[ConceptGraphResponse]) -> list[SearchTarget]:
    targets: dict[str, SearchTarget] = {}
    for concept in concepts:
        contexts: set[tuple[str | None, str | None, str | None]] = {(None, None, None)}
        for mechanism in concept.mechanisms:
            contexts.add((mechanism.mechanism_name, None, None))
            for code in mechanism.code_examples:
                if code.lang or code.framework:
                    contexts.add((mechanism.mechanism_name, code.lang, code.framework))
                    contexts.add((None, code.lang, code.framework))
        for mechanism, lang, framework in sorted(
            contexts, key=lambda item: tuple(v or "" for v in item)
        ):
            queries, _ = build_queries(
                concept.concept_name,
                mechanism,
                lang,
                framework,
                concept.cwe_id,
                concept.owasp_id,
                concept.affected_components,
            )
            for query in queries:
                target = SearchTarget(concept.concept_name, query)
                targets[target.key] = target
    return list(targets.values())


async def collect(
    store: CollectionStore,
    search: Callable[[str], Awaitable[list[VideoCandidate]]],
    *,
    now: int | None = None,
    max_searches: int = 80,
    daily_limit: int = 80,
    refresh_days: int = 7,
    dry_run: bool = False,
    inspect_videos: Callable[[list[str]], Awaitable[list[VideoCandidate]]]
    | None = None,
    max_video_batches: int = 10,
) -> dict:
    if (
        not 1 <= refresh_days <= 27
        or max_searches < 1
        or daily_limit < 1
        or max_video_batches < 0
    ):
        raise ValueError("refresh_days must be 1..27; budgets must be positive")
    clock = (lambda: now) if now is not None else (lambda: int(time.time()))
    report = {
        "status": "completed",
        "searches": 0,
        "updated": 0,
        "failed": 0,
        "pending": 0,
        "metadata_updated": 0,
    }
    await store.initialize()
    token = uuid4().hex
    if not await store.acquire(token, clock()):
        return {**report, "status": "busy"}
    try:
        await store.cleanup(clock())
        targets = build_targets(await store.list_concepts())
        times = await store.pool_times()
        due = [
            target
            for target in targets
            if times.get(target.key, 0) <= clock() - refresh_days * 86400
        ]
        due.sort(key=lambda target: times.get(target.key, 0))
        report["pending"] = len(due)
        if dry_run:
            return {**report, "status": "dry_run"}
        if inspect_videos is not None:
            for _ in range(max_video_batches):
                ids = await store.videos_due(clock())
                if not ids:
                    break
                if not await store.renew(token, clock()):
                    return {**report, "status": "lease_lost"}
                try:
                    metadata = await inspect_videos(ids)
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    log.warning(
                        "youtube_metadata_refresh_failed", error=type(exc).__name__
                    )
                    return {
                        **report,
                        "status": "youtube_unavailable",
                        "failed": report["failed"] + 1,
                    }
                await store.refresh_videos(ids, metadata, clock(), token)
                report["metadata_updated"] += len(metadata)
        for target in due[:max_searches]:
            if not await store.reserve_search(token, clock(), daily_limit):
                report["status"] = "budget_or_lease_exhausted"
                break
            report["searches"] += 1
            try:
                videos = await search(target.query)
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                report["failed"] += 1
                # Never log the exception URL: it can contain the API key.
                log.warning(
                    "youtube_collection_failed",
                    error=type(exc).__name__,
                    pool_key=target.key,
                )
                if isinstance(
                    exc, httpx.HTTPStatusError
                ) and exc.response.status_code in (401, 403, 429):
                    report["status"] = "youtube_unavailable"
                    break
                continue
            await store.replace_pool(target, videos, clock(), token)
            report["updated"] += 1
        report["pending"] -= report["updated"]
        return report
    finally:
        await store.release(token)
