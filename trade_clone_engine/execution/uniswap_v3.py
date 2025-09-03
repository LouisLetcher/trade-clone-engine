from __future__ import annotations

from dataclasses import dataclass

from loguru import logger


@dataclass
class V3SinglePlan:
    router: str
    token_in: str
    token_out: str
    fee: int
    amount_in: int
    min_out: int
    recipient: str
    deadline: int
    value: int


def compute_min_out_single(quoter_contract, token_in: str, token_out: str, fee: int, amount_in: int, slippage_bps: int) -> int:
    try:
        quoted_out = int(
            quoter_contract.functions.quoteExactInputSingle(token_in, token_out, int(fee), int(amount_in), 0).call()
        )
        slip = quoted_out * slippage_bps // 10_000
        return max(0, quoted_out - slip)
    except Exception as e:
        logger.warning("V3 quoteExactInputSingle failed: {} — falling back to zero min_out", e)
        return 0


def build_exact_input_single(router_contract, p: V3SinglePlan):
    params = (
        p.token_in,
        p.token_out,
        int(p.fee),
        p.recipient,
        int(p.deadline),
        int(p.amount_in),
        int(p.min_out),
        0,  # sqrtPriceLimitX96
    )
    return router_contract.functions.exactInputSingle(params).build_transaction({"value": int(p.value)})
