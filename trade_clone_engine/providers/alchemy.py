from __future__ import annotations

import requests


def trace_native_received(alchemy_rpc_url: str, tx_hash: str, to_address: str) -> int | None:
    """
    Uses trace_transaction to find internal value transfers to `to_address` for a given tx.
    Returns the total wei received as a positive int if found.
    """
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "trace_transaction", "params": [tx_hash]}
        r = requests.post(alchemy_rpc_url, json=payload, timeout=15)
        r.raise_for_status()
        traces = r.json().get("result", []) or []
        want = to_address.lower()
        total = 0
        for tr in traces:
            act = tr.get("action", {})
            to = (act.get("to") or "").lower()
            val_hex = act.get("value") or "0x0"
            if to == want and val_hex:
                total += int(val_hex, 16)
        return total if total > 0 else None
    except Exception:
        return None
