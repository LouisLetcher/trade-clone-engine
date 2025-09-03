from __future__ import annotations

import requests


def get_swap_quote(
    base_url: str,
    chain_id: int,
    sell_token: str,
    buy_token: str,
    sell_amount: int,
    taker_address: str,
    slippage_bps: int,
):
    slippage_pct = max(0.0, slippage_bps / 10_000.0)
    # Base URL example: https://api.0x.org or https://base.api.0x.org for Base
    # Use /swap/v1/quote
    url = f"{base_url}/swap/v1/quote"
    params = {
        "sellToken": sell_token,
        "buyToken": buy_token,
        "sellAmount": str(sell_amount),
        "takerAddress": taker_address,
        "slippagePercentage": str(slippage_pct),
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    # Fields: to, data, value, allowanceTarget, buyAmount
    return {
        "to": data.get("to"),
        "data": data.get("data"),
        "value": int(data.get("value") or 0),
        "allowanceTarget": data.get("allowanceTarget"),
        "buyAmount": int(data.get("buyAmount") or 0),
    }
