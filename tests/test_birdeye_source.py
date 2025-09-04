from __future__ import annotations

from typing import Any


def test_birdeye_paging_and_caps(monkeypatch):
    from trade_clone_engine.discovery.sources import BirdeyeSource

    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeResp:
        def __init__(self, ok: bool, payload: dict[str, Any]):
            self.ok = ok
            self._payload = payload
            self.status_code = 200 if ok else 500
            self.text = "ok"

        def json(self):
            return self._payload

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, params or {}))
        offset = (params or {}).get("offset", 0)
        limit = (params or {}).get("limit", 10)
        # Return `limit` items with address field; stop after two pages
        if offset >= 10:
            payload = {"data": {"items": []}}
        else:
            items = [{"address": f"addr{offset + i}"} for i in range(limit)]
            payload = {"data": {"items": items}}
        return FakeResp(True, payload)

    monkeypatch.setenv("TCE_BIRDEYE_API_KEY", "x")
    monkeypatch.setenv("TCE_BIRDEYE_CHAIN", "solana")
    monkeypatch.setenv("TCE_BIRDEYE_LIMIT", "7")  # per request
    monkeypatch.setenv("TCE_BIRDEYE_TOTAL_LIMIT", "12")  # total cap
    monkeypatch.setattr("requests.get", fake_get)

    src = BirdeyeSource(api_key="x")
    out = src.top_wallets(limit=50)
    # Capped to 12
    assert len(out) == 12
    # First address present
    assert any(w["address"] == "addr0" for w in out)
    # Verify paging happened at least twice
    assert len(calls) >= 2


def test_birdeye_error_returns_empty(monkeypatch):
    from trade_clone_engine.discovery.sources import BirdeyeSource

    class FakeResp:
        ok = False
        status_code = 429
        text = "Too many requests"

        def json(self):  # pragma: no cover
            return {}

    def fake_get(url, headers=None, params=None, timeout=None):
        return FakeResp()

    monkeypatch.setenv("TCE_BIRDEYE_API_KEY", "x")
    monkeypatch.setattr("requests.get", fake_get)
    src = BirdeyeSource(api_key="x")
    out = src.top_wallets(limit=5)
    assert out == []
