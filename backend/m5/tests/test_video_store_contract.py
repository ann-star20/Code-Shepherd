from app import video_store
from app.video_models import SearchTarget


async def test_pool_write_uses_driver_compatible_parameters_and_deduplicates(
    monkeypatch,
):
    class Result:
        async def single(self):
            return {"key": "pool"}

        async def consume(self):
            pass

    class Transaction:
        def __init__(self):
            self.calls = []

        async def run(self, query, **parameters):
            self.calls.append((query, parameters))
            return Result()

    tx = Transaction()

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute_write(self, callback):
            await callback(tx)

    class Driver:
        def session(self, **kwargs):
            return Session()

    monkeypatch.setattr(video_store, "get_driver", lambda: Driver())
    video = {
        "video_id": "example",
        "title": "first",
        "url": "https://example.test",
        "thumbnail": None,
        "channel_title": None,
    }
    await video_store.Neo4jVideoStore().replace_pool(
        SearchTarget("SQLi", "django SQLi"),
        [video, {**video, "title": "duplicate"}],
        100,
        "lease",
    )
    assert tx.calls[0][1]["search_query"] == "django SQLi"
    assert tx.calls[2][1]["videos"] == [{**video, "position": 0}]
