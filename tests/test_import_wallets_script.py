import importlib.util
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("import_wallets", str(path))
    assert spec and spec.loader, "Failed to load module spec"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


def test_import_wallets_parse_and_upsert(tmp_path):
    mod = load_module(Path("scripts/import_wallets.py"))

    payload = [
        {"address": "0xAbCdEf0123456789aBCdef0123456789AbCdEf01"},
        {"wallet": "9xQeWvG816bUx9EPm2Tbd2Ykqg3k9uADuZbL9g1z3Q2E"},
    ]
    addrs = mod.parse_addresses(payload)
    assert len(addrs) == 2

    wallets_yaml = tmp_path / "wallets.yaml"
    wallets_yaml.write_text("wallets: []\n")
    data = mod.load_wallets_yaml(wallets_yaml)
    wallets = data.get("wallets", [])
    defaults = {"notes": "test", "copy_ratio": 0.2, "slippage_bps": 300, "max_native_in_wei": 0, "allowed_tokens": [], "denied_tokens": []}
    for a in addrs:
        mod.upsert(wallets, "solana" if not a.startswith("0x") else "evm", a, defaults)
    data["wallets"] = wallets
    mod.save_wallets_yaml(wallets_yaml, data)

    out = mod.load_wallets_yaml(wallets_yaml)
    assert len(out["wallets"]) == 2
    # EVM lowercased, Solana preserved
    evm = next(w for w in out["wallets"] if w["address"].startswith("0x"))
    sol = next(w for w in out["wallets"] if not w["address"].startswith("0x"))
    assert evm["address"] == "0xabcdef0123456789abcdef0123456789abcdef01"
    assert sol["address"] == "9xQeWvG816bUx9EPm2Tbd2Ykqg3k9uADuZbL9g1z3Q2E"
