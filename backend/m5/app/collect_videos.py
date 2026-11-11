"""Run once from a scheduler, or --watch in the optional Compose collector."""

import argparse
import asyncio
import json
import os
import time

from neo4j.exceptions import (
    ConfigurationError,
    Neo4jError,
    ServiceUnavailable,
    SessionExpired,
)
from shared.logging import configure_logging

from app.neo4j_client import close_driver
from app.video_collection import collect
from app.video_store import LeaseLostError, Neo4jVideoStore
from app.youtube_client import fetch_video_metadata, search_candidates


async def run_once(**options: object) -> dict:
    from app import mock_data

    if mock_data.enabled():
        return {"status": "mock_mode_read_only", "searches": 0}
    store = Neo4jVideoStore()
    try:
        if not options.get("dry_run") and not os.getenv("YOUTUBE_API_KEY"):
            await store.initialize()
            await store.cleanup(int(time.time()))
            return {"status": "missing_api_key"}
        return await collect(
            store, search_candidates, inspect_videos=fetch_video_metadata, **options
        )
    except (Neo4jError, ServiceUnavailable, SessionExpired, ConfigurationError):
        return {"status": "database_unavailable"}
    except LeaseLostError:
        return {"status": "lease_lost"}
    finally:
        await close_driver()


async def run(args: argparse.Namespace) -> int:
    configure_logging()
    while True:
        result = await run_once(
            max_searches=args.max_searches,
            daily_limit=args.daily_limit,
            refresh_days=args.refresh_days,
            dry_run=args.dry_run,
            max_video_batches=args.max_video_batches,
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if not args.watch:
            return (
                2
                if result["status"]
                in (
                    "database_unavailable",
                    "missing_api_key",
                    "lease_lost",
                    "youtube_unavailable",
                )
                or result.get("failed", 0)
                else 0
            )
        await asyncio.sleep(args.interval_hours * 3600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-searches", type=int, default=80)
    parser.add_argument("--daily-limit", type=int, default=80)
    parser.add_argument("--refresh-days", type=int, default=7)
    parser.add_argument("--max-video-batches", type=int, default=10)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect pending queries without calling YouTube; still performs DB retention cleanup",
    )
    parser.add_argument(
        "--watch", action="store_true", help="Repeat collection, default every 24 hours"
    )
    parser.add_argument("--interval-hours", type=float, default=24)
    args = parser.parse_args()
    if (
        args.max_searches < 1
        or args.daily_limit < 1
        or not 1 <= args.refresh_days <= 27
        or args.interval_hours <= 0
        or args.max_video_batches < 0
    ):
        parser.error(
            "budgets and interval must be positive; refresh-days must be 1..27"
        )
    try:
        raise SystemExit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
