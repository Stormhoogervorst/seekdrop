import asyncio

from nicotine_sync import updates
from nicotine_sync.updates import UpdateChecker, is_newer, parse_version


def test_version_compare():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert is_newer("v0.3.0", "0.2.0")
    assert is_newer("0.2.1", "0.2")
    assert not is_newer("v0.2.0", "0.2.0")
    assert not is_newer("v0.1.9", "0.2.0")
    assert not is_newer("nightly", "0.2.0")


class _Store:
    class settings:
        check_updates = True


def test_check_sets_latest(monkeypatch):
    class Resp:
        status = 200
        async def json(self): return {"tag_name": "v9.0.0", "html_url": "https://github.com/x/y/releases/tag/v9.0.0"}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    class Sess:
        def __init__(self, **kw): pass
        def get(self, url, timeout=None):
            assert url.endswith("/releases/latest")
            return Resp()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    monkeypatch.setattr(updates.aiohttp, "ClientSession", Sess)
    c = UpdateChecker(_Store(), repo="x/y")
    asyncio.run(c.check())
    assert c.latest == {"version": "9.0.0", "url": "https://github.com/x/y/releases/tag/v9.0.0"}
