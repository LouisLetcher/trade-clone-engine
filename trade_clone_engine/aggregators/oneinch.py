from __future__ import annotations

import requests


def get_swap_quote(
    base_url: str,
    chain_id: int,
    src_token: str,
    dst_token: str,
    amount_in: int,
    from_address: str,
    slippage_bps: int,
    api_key: str | None = None,
):
    slippage = max(0.0, slippage_bps / 100.0)
    url = f"{base_url}/{chain_id}/swap"
    params = {
        "fromTokenAddress": src_token,
        "toTokenAddress": dst_token,
        "amount": str(amount_in),
        "fromAddress": from_address,
        "slippage": str(slippage),
        "disableEstimate": "false",
    }
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    # Expected fields: tx { to, data, value }, toTokenAmount, protocols
    tx = data.get("tx", {})
    to_token_amount = int(data.get("toTokenAmount", 0))
    spender = data.get("router") or data.get("spender")  # varies by version
    return {
        "to": tx.get("to"),
        "data": tx.get("data"),
        "value": int(tx.get("value") or 0),
        "allowanceTarget": spender,
        "buyAmount": to_token_amount,
    }
