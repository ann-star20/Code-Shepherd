from neo4j.exceptions import ServiceUnavailable

from app import collect_videos as cli


async def test_cli_returns_controlled_status_without_neo4j(monkeypatch):
    class OfflineStore:
        async def initialize(self):
            raise ServiceUnavailable("private host")

    monkeypatch.setattr(cli, "Neo4jVideoStore", OfflineStore)
    result = await cli.run_once(dry_run=True)
    assert result == {"status": "database_unavailable"}


async def test_cli_missing_key_does_not_consume_search_budget(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    class Store:
        async def initialize(self):
            pass

        async def cleanup(self, now):
            pass

    monkeypatch.setattr(cli, "Neo4jVideoStore", Store)
    assert await cli.run_once() == {"status": "missing_api_key"}
