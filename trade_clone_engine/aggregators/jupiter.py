from __future__ import annotations

import requests


def get_quote(quote_url: str, input_mint: str, output_mint: str, amount: int, slippage_bps: int):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
        "onlyDirectRoutes": "false",
    }
    r = requests.get(quote_url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    # Return the first route
    routes = data.get("data") or []
    return routes[0] if routes else None


def get_swap_transaction(swap_url: str, route: dict, user_public_key: str):
    payload = {
        "route": route,
        "userPublicKey": user_public_key,
        "wrapAndUnwrapSol": True,
        "useTokenLedger": False,
        "asLegacyTransaction": False,
        "useSharedAccounts": True,
    }
    r = requests.post(swap_url, json=payload, timeout=20)
    r.raise_for_status()
    j = r.json()
    return j.get("swapTransaction")
