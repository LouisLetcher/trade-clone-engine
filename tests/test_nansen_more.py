from __future__ import annotations

from typing import Any


def test_nansen_dcas_post_body_and_parse(monkeypatch):
    from trade_clone_engine.discovery.sources import NansenSource

    captured: dict[str, Any] = {}

    class FakeResp:
        def __init__(self, ok: bool, payload: dict[str, Any]):
            self.ok = ok
            self._payload = payload
            self.text = "ok"

        def json(self):
            return self._payload

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["json"] = json or {}
        payload = {
            "data": [
                {"trader_address": "9xQe...Sol", "chain": "solana"},
                {"trader_address": "0xAbCdEf0123456789aBCdef0123456789AbCdEf01", "chain": "ethereum"},
            ],
            "pagination": {"page": 1, "per_page": 2, "is_last_page": True},
        }
        return FakeResp(True, payload)

    monkeypatch.setenv("TCE_DISCOVER_ALLOWED_LABELS", "")
    monkeypatch.setenv("TCE_DISCOVER_DENIED_LABELS", "")
    monkeypatch.setenv("TCE_NANSEN_PER_PAGE", "10")
    monkeypatch.setattr("requests.post", fake_post)

    src = NansenSource(
        api_key="test-key",
        base_url="https://api.nansen.ai/api/v1",
        endpoint_path="smart-money/dcas",
    )
    out = src.top_wallets(limit=2)
    assert captured["url"].endswith("/api/v1/smart-money/dcas")
    assert len(out) == 2


def test_nansen_top_traders_get_parse(monkeypatch):
    from trade_clone_engine.discovery.sources import NansenSource

    class FakeResp:
        def __init__(self, ok: bool, payload: dict[str, Any]):
            self.ok = ok
            self._payload = payload
            self.text = "ok"

        def json(self):
            return self._payload

    def fake_get(url, headers=None, timeout=None):
        payload = {
            "items": [
                {"address": "0xAbCdEf0123456789aBCdef0123456789AbCdEf01"},
                {"address": "9xQe...Sol"},
            ]
        }
        return FakeResp(True, payload)

    monkeypatch.setattr("requests.get", fake_get)
    src = NansenSource(api_key="k", base_url="https://api.nansen.ai/api/v1", endpoint_path="smart-money/top-traders?timeRange=7d")
    out = src.top_wallets(limit=2)
    addrs = {w["address"] for w in out}
    assert "0xabcdef0123456789abcdef0123456789abcdef01" in addrs
    assert "9xQe...Sol" in addrs
