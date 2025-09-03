from __future__ import annotations

import requests
from typing import Optional


CHAIN_TO_COINGECKO_PLATFORM = {
    1: "ethereum",
    8453: "base",
}


def get_token_price_usd(chain_id: int, token_address: Optional[str], native_symbol: str = "ETH") -> Optional[float]:
    if not token_address:
        # Native coin
        if chain_id == 1:
            ids = "ethereum"
        elif chain_id == 8453:
            ids = "ethereum"  # Base native is ETH
        else:
            return None
        r = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ids, "vs_currencies": "usd"}, timeout=10)
        if r.ok:
            return float(r.json().get(ids, {}).get("usd"))
        return None

    platform = CHAIN_TO_COINGECKO_PLATFORM.get(chain_id)
    if not platform:
        return None
    r = requests.get(
        f"https://api.coingecko.com/api/v3/simple/token_price/{platform}",
        params={"contract_addresses": token_address, "vs_currencies": "usd"},
        timeout=10,
    )
    if not r.ok:
        return None
    data = r.json() or {}
    token_key = token_address.lower()
    rec = data.get(token_key)
    if not rec:
        # Some responses use checksum
        rec = next(iter(data.values()), None)
    if not rec:
        return None
    return float(rec.get("usd")) if rec.get("usd") is not None else None

