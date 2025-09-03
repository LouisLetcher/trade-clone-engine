from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml


def load_wallets_yaml(path: Path) -> dict:
    if not path.exists():
        return {"wallets": []}
    return yaml.safe_load(path.read_text()) or {"wallets": []}


def save_wallets_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def parse_addresses(payload: Any) -> list[str]:
    # Accept a list of strings, list of objects with 'address', or newline-separated strings
    if isinstance(payload, list):
        if all(isinstance(x, str) for x in payload):
            return [x for x in payload if x]
        if all(isinstance(x, dict) for x in payload):
            addrs: list[str] = []
            for row in payload:
                a = row.get("address") or row.get("wallet") or row.get("walletAddress")
                if a:
                    addrs.append(a)
            return addrs
    if isinstance(payload, str):
        return [line.strip() for line in payload.splitlines() if line.strip()]
    return []


def upsert(wallets: list[dict], chain: str, address: str, defaults: dict) -> None:
    norm_addr = address.lower() if address.startswith("0x") else address
    for w in wallets:
        if (w.get("address") == norm_addr) and (str(w.get("chain") or "").lower() == chain.lower()):
            # Update missing fields only
            for k, v in defaults.items():
                if w.get(k) in (None, ""):
                    w[k] = v
            return
    item = {"chain": chain, "address": norm_addr}
    item.update(defaults)
    wallets.append(item)


def main() -> int:
    p = argparse.ArgumentParser(description="Import wallets into config/wallets.yaml")
    p.add_argument("--input", "-i", help="Input file (JSON array or newline-separated addresses). If omitted, reads stdin.")
    p.add_argument("--chain", default="solana", help="Chain for imported wallets: solana|evm (default: solana)")
    p.add_argument("--wallets-yaml", default="config/wallets.yaml", help="Path to wallets.yaml")
    p.add_argument("--copy-ratio", type=float, default=0.2)
    p.add_argument("--slippage-bps", type=int, default=300)
    p.add_argument("--max-native-in-wei", type=int, default=0)
    p.add_argument("--prune-others", action="store_true", help="Remove wallets of other chains before importing")
    args = p.parse_args()

    # Load input
    if args.input:
        raw = Path(args.input).read_text()
    else:
        raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
    except Exception:
        payload = raw

    addrs = parse_addresses(payload)
    if not addrs:
        print("No addresses parsed from input", file=sys.stderr)
        return 1

    path = Path(args.wallets_yaml)
    data = load_wallets_yaml(path)
    wallets: list[dict] = data.get("wallets", [])
    if args.prune_others:
        wallets = [w for w in wallets if str((w.get("chain") or "")).lower() == args.chain.lower()]

    defaults = {
        "notes": "imported via MCP",
        "copy_ratio": args.copy_ratio,
        "slippage_bps": args.slippage_bps,
        "max_native_in_wei": args.max_native_in_wei,
        "allowed_tokens": [],
        "denied_tokens": [],
    }

    for a in addrs:
        upsert(wallets, args.chain, a, defaults)

    data["wallets"] = wallets
    save_wallets_yaml(path, data)
    print(f"Imported {len(addrs)} addresses into {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

