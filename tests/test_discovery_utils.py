from importlib.machinery import SourceFileLoader
from pathlib import Path


def test_rank_wallets_filters_and_limits():
    from trade_clone_engine.discovery.sources import rank_wallets

    cand = [
        {"address": "0x1", "chain": "evm", "pnl_usd": 10, "win_rate": 0.5, "trades": 5},
        {"address": "0x2", "chain": "evm", "pnl_usd": 100, "win_rate": 0.8, "trades": 50},
        {"address": "SoLanaAddr", "chain": "solana", "pnl_usd": 50, "win_rate": 0.7, "trades": 20},
    ]
    top = rank_wallets(cand, min_trades=10, top_percent=50.0)
    # 0x1 filtered out (trades < 10). Remaining 2 => top 50% => 1 item, highest by pnl then win_rate
    assert len(top) == 1
    assert top[0]["address"] == "0x2"


def test_nansen_generic_extractor(tmp_path):
    from trade_clone_engine.discovery.sources import NansenSource

    src = NansenSource(api_key="test")
    payload = {
        "data": {
            "items": [
                {"buyer": "0xAbCDEF0123456789abcdef0123456789AbCdEf01"},
                {"to": "9xQeWvG816bUx9EPm2Tbd2Ykqg3k9uADuZbL9g1z3Q2E"},
            ]
        }
    }
    addrs = src._extract_addresses_generic(payload)
    assert any(a.startswith("0x") for a in addrs)
    assert any(len(a) >= 32 and not a.startswith("0x") for a in addrs)

