from __future__ import annotations

from dataclasses import dataclass

from loguru import logger


@dataclass
class V2SwapPlan:
    method: str
    router: str
    path: list[str]
    amount_in: int
    min_out: int
    recipient: str
    deadline: int
    value: int  # native value to send


def compute_min_out(router_contract, amount_in: int, path: list[str], slippage_bps: int) -> int:
    try:
        amounts = router_contract.functions.getAmountsOut(amount_in, path).call()
        quoted_out = int(amounts[-1])
        slip = quoted_out * slippage_bps // 10_000
        return max(0, quoted_out - slip)
    except Exception as e:
        logger.warning("getAmountsOut failed: {} — falling back to zero min_out", e)
        return 0


def build_swap_exact_eth_for_tokens(router_contract, plan: V2SwapPlan):
    return router_contract.functions.swapExactETHForTokens(
        plan.min_out, plan.path, plan.recipient, plan.deadline
    ).build_transaction({"value": plan.value})


def build_swap_exact_tokens_for_eth(router_contract, plan: V2SwapPlan):
    return router_contract.functions.swapExactTokensForETH(
        plan.amount_in, plan.min_out, plan.path, plan.recipient, plan.deadline
    ).build_transaction({})


def build_swap_exact_tokens_for_tokens(router_contract, plan: V2SwapPlan):
    return router_contract.functions.swapExactTokensForTokens(
        plan.amount_in, plan.min_out, plan.path, plan.recipient, plan.deadline
    ).build_transaction({})
