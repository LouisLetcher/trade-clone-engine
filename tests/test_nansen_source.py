from __future__ import annotations

from typing import Any


def test_nansen_dex_trades_post_body_and_parse(monkeypatch):
    from trade_clone_engine.discovery.sources import NansenSource

    captured: dict[str, Any] = {}

    class FakeResp:
        def __init__(self, ok: bool, payload: dict[str, Any]):
            self.ok = ok
            self._payload = payload
            self.text = "ok"

        def json(self):
            return self._payload

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002 - shadow ok in tests
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["json"] = json or {}
        payload = {
            "data": [
                {
                    "trader_address": "9xQeWvG816bUx9EPm2Tbd2Ykqg3k9uADuZbL9g1z3Q2E",
                    "chain": "solana",
                },
                {
                    "trader_address": "0xAbCdEf0123456789aBCdef0123456789AbCdEf01",
                    "chain": "ethereum",
                },
            ],
            "pagination": {"page": 1, "per_page": 2, "is_last_page": True},
        }
        return FakeResp(True, payload)

    monkeypatch.setenv("TCE_DISCOVER_CHAIN", "solana")
    monkeypatch.setenv("TCE_DISCOVER_ALLOWED_LABELS", "Fund,Smart Trader")
    monkeypatch.setenv("TCE_DISCOVER_DENIED_LABELS", "30D Smart Trader")
    monkeypatch.setenv("TCE_NANSEN_PER_PAGE", "77")

    monkeypatch.setattr("requests.post", fake_post)

    src = NansenSource(
        api_key="test-key",
        base_url="https://api.nansen.ai/api/v1",
        endpoint_path="smart-money/dex-trades?timeRange=24h",
    )
    out = src.top_wallets(limit=2)

    # Verify request construction
    assert captured["url"].endswith("/api/v1/smart-money/dex-trades?timeRange=24h")
    hdrs = captured["headers"]
    assert hdrs.get("NANSEN-API-KEY") == "test-key" or hdrs.get("apiKey") == "test-key"
    body = captured["json"]
    assert body["pagination"]["per_page"] == 77
    assert body.get("chains") == ["solana"]
    assert set(body.get("filters", {}).get("include_smart_money_labels", [])) == {
        "Fund",
        "Smart Trader",
    }
    assert set(body.get("filters", {}).get("exclude_smart_money_labels", [])) == {
        "30D Smart Trader"
    }

    # Verify parsing
    addrs = {w["address"] for w in out}
    assert "9xQeWvG816bUx9EPm2Tbd2Ykqg3k9uADuZbL9g1z3Q2E" in addrs
    assert "0xabcdef0123456789abcdef0123456789abcdef01" in addrs  # lowercased EVM
