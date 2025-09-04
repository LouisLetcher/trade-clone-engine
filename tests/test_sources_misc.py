from __future__ import annotations


def test_dune_source_handles_missing_query_id(monkeypatch):
    from trade_clone_engine.discovery.sources import DuneSource

    src = DuneSource(api_key="k", query_id=None)
    out = src.top_wallets(limit=5)
    assert out == []


def test_dune_source_parses_rows(monkeypatch):
    from trade_clone_engine.discovery.sources import DuneSource

    class FakeResp:
        ok = True

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, headers=None, timeout=None):
        payload = {"result": {"rows": [{"wallet": "0xAbCdE"}, {"address": "0x1234"}]}}
        return FakeResp(payload)

    monkeypatch.setattr("requests.get", fake_get)
    src = DuneSource(api_key="k", query_id=1)
    out = src.top_wallets(limit=5)
    addrs = {w["address"] for w in out}
    assert "0xabcde" in addrs
    assert "0x1234" in addrs


def test_nansen_generic_fallback(monkeypatch):
    from trade_clone_engine.discovery.sources import NansenSource

    class FakeResp:
        ok = True

        def json(self):
            # No data/items/results; ensure generic extractor finds nested addresses
            return {
                "root": {
                    "owner": "0xAbCdEf0123456789aBCdef0123456789AbCdEf01",
                    "toAddress": "9xQe...Sol",
                }
            }

    def fake_get(url, headers=None, timeout=None):
        return FakeResp()

    monkeypatch.setattr("requests.get", fake_get)
    src = NansenSource(
        api_key="k", base_url="https://api.nansen.ai/api/v1", endpoint_path="anything"
    )
    out = src.top_wallets(limit=2)
    addrs = {w["address"] for w in out}
    assert "0xabcdef0123456789abcdef0123456789abcdef01" in addrs


def test_nansen_error_returns_empty(monkeypatch):
    from trade_clone_engine.discovery.sources import NansenSource

    class FakeResp:
        ok = False
        text = "Not Found"

        def json(self):  # pragma: no cover
            return {}

    def fake_get(url, headers=None, timeout=None):
        return FakeResp()

    monkeypatch.setattr("requests.get", fake_get)
    src = NansenSource(
        api_key="k",
        base_url="https://api.nansen.ai/api/v1",
        endpoint_path="smart-money/top-traders?timeRange=7d",
    )
    out = src.top_wallets(limit=5)
    assert out == []
