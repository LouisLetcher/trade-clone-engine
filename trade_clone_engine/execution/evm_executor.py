from __future__ import annotations

import json
import time
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from web3 import Web3

from trade_clone_engine.aggregators import oneinch as agg_oneinch
from trade_clone_engine.aggregators import zeroex as agg_zeroex
from trade_clone_engine.analytics.pricing import get_token_price_usd
from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import ExecutedTrade, ObservedTrade, session_scope
from trade_clone_engine.execution.evm_wallet import EvmWallet
from trade_clone_engine.execution.uniswap_v2 import (
    V2SwapPlan,
    build_swap_exact_eth_for_tokens,
    build_swap_exact_tokens_for_eth,
    build_swap_exact_tokens_for_tokens,
    compute_min_out,
)
from trade_clone_engine.execution.uniswap_v3 import (
    V3SinglePlan,
    build_exact_input_single,
    compute_min_out_single,
)
from trade_clone_engine.providers.alchemy import trace_native_received


class EvmExecutor:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.wallet = EvmWallet.create(
            rpc_url=settings.evm_rpc_ws_url,
            chain_id=settings.evm_chain_id,
            private_key=settings.evm_private_key,
            explicit_address=settings.executor_address,
        )

        # Load ABIs for decoding inputs (same as watcher)
        abi_dir = Path(__file__).resolve().parent.parent / "abi"
        self.v2_abi = json.loads((abi_dir / "uniswap_v2_router.json").read_text())
        self.v3_abi = json.loads((abi_dir / "uniswap_v3_router.json").read_text())
        self.v3_quoter_abi = json.loads((abi_dir / "uniswap_v3_quoter.json").read_text())
        # Dummy contracts for decoding only
        dummy = "0x0000000000000000000000000000000000000000"
        self.v2_decoder = self.wallet.w3.eth.contract(address=dummy, abi=self.v2_abi)
        self.v3_decoder = self.wallet.w3.eth.contract(address=dummy, abi=self.v3_abi)

    def _try_aggregator(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        is_native_in: bool,
        slippage_bps: int,
    ) -> tuple[str | None, int | None]:
        # Select aggregator per-chain override if provided
        agg_name = (
            getattr(self.settings, f"aggregator_chain_{self.settings.evm_chain_id}", None)
            or self.settings.aggregator
        )
        if not agg_name:
            return None, None
        agg = agg_name.lower()
        try:
            if agg == "1inch":
                base_url = self.settings.oneinch_base_url
                q = agg_oneinch.get_swap_quote(
                    base_url=base_url,
                    chain_id=self.settings.evm_chain_id,
                    src_token=(
                        "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE" if is_native_in else token_in
                    ),
                    dst_token=token_out,
                    amount_in=amount_in,
                    from_address=self.wallet.address,
                    slippage_bps=slippage_bps,
                    api_key=self.settings.oneinch_api_key,
                )
                allowance_target = q.get("allowanceTarget")
                if allowance_target and (not is_native_in) and (not self.settings.dry_run):
                    erc20 = self.wallet.erc20(token_in)
                    allowance = int(erc20.functions.allowance(self.wallet.address, allowance_target).call())
                    if allowance < amount_in:
                        tx = erc20.functions.approve(allowance_target, amount_in).build_transaction({"from": self.wallet.address})
                        _txh = self.wallet.send_tx(tx)
                tx = {
                    "to": q["to"],
                    "data": q["data"],
                    "value": int(q.get("value") or 0),
                    "from": self.wallet.address,
                }
                if self.settings.dry_run:
                    return None, int(q.get("buyAmount") or 0)
                txh = self.wallet.send_tx(tx)
                return txh, int(q.get("buyAmount") or 0)
            elif agg == "0x":
                if self.settings.evm_chain_id == 1:
                    base_url = self.settings.zeroex_base_url
                elif self.settings.evm_chain_id == 137:
                    base_url = self.settings.zeroex_base_url_polygon
                elif self.settings.evm_chain_id == 8453:
                    base_url = self.settings.zeroex_base_url_base_chain
                else:
                    base_url = self.settings.zeroex_base_url
                q = agg_zeroex.get_swap_quote(
                    base_url=base_url,
                    chain_id=self.settings.evm_chain_id,
                    sell_token=("ETH" if is_native_in else token_in),
                    buy_token=token_out,
                    sell_amount=amount_in,
                    taker_address=self.wallet.address,
                    slippage_bps=slippage_bps,
                )
                allowance_target = q.get("allowanceTarget")
                if allowance_target and (not is_native_in) and (not self.settings.dry_run):
                    erc20 = self.wallet.erc20(token_in)
                    allowance = int(erc20.functions.allowance(self.wallet.address, allowance_target).call())
                    if allowance < amount_in:
                        tx = erc20.functions.approve(allowance_target, amount_in).build_transaction({"from": self.wallet.address})
                        _txh = self.wallet.send_tx(tx)
                tx = {
                    "to": q["to"],
                    "data": q["data"],
                    "value": int(q.get("value") or 0),
                    "from": self.wallet.address,
                }
                if self.settings.dry_run:
                    return None, int(q.get("buyAmount") or 0)
                txh = self.wallet.send_tx(tx)
                return txh, int(q.get("buyAmount") or 0)
        except Exception as _e:
            logger.warning("Aggregator failed, falling back to router: {}", _e)
        return None, None

    def run(self, SessionFactory):
        logger.info("Starting EVM executor (dry_run={})", self.settings.dry_run)
        while True:
            try:
                with session_scope(SessionFactory) as s:
                    rec: ObservedTrade | None = (
                        s.execute(
                            select(ObservedTrade)
                            .where(ObservedTrade.processed.is_(False))
                            .order_by(ObservedTrade.id.asc())
                            .limit(1)
                        )
                        .scalars()
                        .first()
                    )
                    if not rec:
                        time.sleep(1.5)
                        continue

                    status = "skipped"
                    tx_hash = None
                    err = None
                    gas_spent = None

                    logger.info("Processing observed trade {}: method={} dex={}", rec.id, rec.method, rec.dex)

                    # Decode to retrieve method + params (esp. path & amounts)
                    method = rec.method
                    params = None
                    try:
                        func, params = self.v2_decoder.decode_function_input(rec.raw_input)
                        method = func.fn_name
                        decoded_is_v2 = True
                    except Exception:
                        try:
                            func, params = self.v3_decoder.decode_function_input(rec.raw_input)
                            method = func.fn_name
                            decoded_is_v2 = False
                        except Exception:
                            decoded_is_v2 = False
                            params = None

                    overrides = self.settings.wallet_overrides().get((rec.wallet or "").lower(), {})
                    eff_copy_ratio = float(overrides.get("copy_ratio", self.settings.copy_ratio))
                    eff_slippage_bps = int(overrides.get("slippage_bps", self.settings.slippage_bps))
                    eff_max_native = int(overrides.get("max_native_in_wei", self.settings.max_native_in_wei or 0))
                    allowed = set([a.lower() for a in overrides.get("allowed_tokens", [])])
                    denied = set([a.lower() for a in overrides.get("denied_tokens", [])])

                    def tokens_ok(tokens: list[str], allowed=allowed, denied=denied) -> bool:
                        toks = [t.lower() for t in tokens if t]
                        return not any(t in denied for t in toks) and (not allowed or all(t in allowed for t in toks))

                    # Support V2 and V3
                    if decoded_is_v2 and method in (
                        "swapExactETHForTokens",
                        "swapExactTokensForETH",
                        "swapExactTokensForTokens",
                    ):
                        try:
                            router_addr = Web3.to_checksum_address(rec.dex)
                            router = self.wallet.router_v2(router_addr)

                            # Build path and input amount
                            path = [Web3.to_checksum_address(a) for a in params.get("path", [])]
                            if not tokens_ok(path):
                                status = "skipped"
                                err = "Tokens not allowed by policy"
                                raise Exception(err)
                            observed_amount_in = int(params.get("amountIn") or 0)
                            native_value = 0
                            if method == "swapExactETHForTokens":
                                # amountIn is not in params; use tx value from ObservedTrade.amount_in_wei
                                observed_amount_in = int(rec.amount_in_wei or 0)
                                native_value = int(observed_amount_in * max(0.0, eff_copy_ratio))
                            else:
                                observed_amount_in = int(observed_amount_in)

                            use_amount_in = int(observed_amount_in * max(0.0, eff_copy_ratio))
                            if eff_max_native and method == "swapExactETHForTokens":
                                use_amount_in = min(use_amount_in, int(eff_max_native))
                                native_value = use_amount_in

                            recipient = self.wallet.address or "0x0000000000000000000000000000000000000000"
                            deadline = int(time.time()) + int(self.settings.tx_deadline_seconds)

                            # Compute minOut via getAmountsOut with slippage applied
                            min_out = compute_min_out(router, use_amount_in, path, eff_slippage_bps)

                            plan = V2SwapPlan(
                                method=method,
                                router=router_addr,
                                path=path,
                                amount_in=use_amount_in,
                                min_out=min_out,
                                recipient=recipient,
                                deadline=deadline,
                                value=native_value,
                            )

                            # For token-in routes, ensure allowance
                            if method in ("swapExactTokensForETH", "swapExactTokensForTokens") and not self.settings.dry_run:
                                token_in = path[0]
                                erc20 = self.wallet.erc20(token_in)
                                allowance = int(
                                    erc20.functions.allowance(self.wallet.address, router_addr).call()
                                )
                                if allowance < use_amount_in:
                                    logger.info("Approving router {} for {} wei of {}", router_addr, use_amount_in, token_in)
                                    tx = erc20.functions.approve(router_addr, use_amount_in).build_transaction(
                                        {"from": self.wallet.address}
                                    )
                                    tx_hash = self.wallet.send_tx(tx)
                                    logger.info("Approve tx: {}", tx_hash)

                            # Try aggregator first if configured
                            amount_out_est = None
                            is_native_in = method == "swapExactETHForTokens"
                            agg_txh, agg_buy = self._try_aggregator(path[0], path[-1], use_amount_in, is_native_in, eff_slippage_bps)
                            skip_router = False
                            if agg_txh is not None:
                                tx_hash = agg_txh
                                status = "success"
                                amount_out_est = agg_buy
                                skip_router = True
                            elif agg_buy is not None:
                                # dry-run estimate via aggregator
                                status = "skipped"
                                amount_out_est = agg_buy
                                skip_router = True

                            # Build the swap via router if not using aggregator
                            if not skip_router:
                                if method == "swapExactETHForTokens":
                                    tx = build_swap_exact_eth_for_tokens(router, plan)
                                elif method == "swapExactTokensForETH":
                                    tx = build_swap_exact_tokens_for_eth(router, plan)
                                else:
                                    tx = build_swap_exact_tokens_for_tokens(router, plan)

                                if self.settings.dry_run:
                                    status = "skipped"
                                else:
                                    tx.setdefault("from", self.wallet.address)
                                    if plan.value:
                                        tx["value"] = plan.value
                                    # Respect gas overrides if provided
                                    if self.settings.max_fee_gwei is not None:
                                        tx["maxFeePerGas"] = self.wallet.w3.to_wei(self.settings.max_fee_gwei, "gwei")
                                    if self.settings.max_priority_fee_gwei is not None:
                                        tx["maxPriorityFeePerGas"] = self.wallet.w3.to_wei(
                                            self.settings.max_priority_fee_gwei, "gwei"
                                        )

                                tx_hash = self.wallet.send_tx(tx)
                                status = "success"
                                # Parse receipt for realized gas and output amount (ERC20 only)
                                try:
                                    rcpt = self.wallet.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                                    if rcpt and rcpt.get("status") == 1:
                                        gas_used = rcpt.get("gasUsed")
                                        eff = rcpt.get("effectiveGasPrice")
                                        if gas_used is not None and eff is not None:
                                            gas_spent = str(int(gas_used) * int(eff))
                                        # If token_out is ERC20, parse Transfer to our address
                                        if rec.token_out:
                                            transfer_sig = self.wallet.w3.keccak(text="Transfer(address,address,uint256)").hex()
                                            to_addr = (self.wallet.address or "").lower()
                                            for lg in rcpt.get("logs", []):
                                                if (
                                                    lg.get("address", "").lower() == rec.token_out.lower()
                                                    and lg.get("topics", [])[0].hex() == transfer_sig
                                                    and len(lg.get("topics", [])) >= 3
                                                    and to_addr
                                                ):
                                                    topic_to = lg["topics"][2].hex()
                                                    addr = "0x" + topic_to[-40:]
                                                        if addr.lower() == to_addr:
                                                            val = int(lg.get("data", "0x0"), 16)
                                                            amount_out_est = val
                                                            break
                                        else:
                                            # Native out (ETH) via WETH Withdrawal event to our address
                                            wrapped = self.settings.dex_routers.native_wrapped.get(self.settings.evm_chain_id)
                                            if wrapped:
                                                withdraw_sig = self.wallet.w3.keccak(text="Withdrawal(address,uint256)").hex()
                                                to_addr = (self.wallet.address or "").lower()
                                            for lg in rcpt.get("logs", []):
                                                if (
                                                    lg.get("address", "").lower() == wrapped.lower()
                                                    and lg.get("topics", [])[0].hex() == withdraw_sig
                                                    and len(lg.get("topics", [])) >= 2
                                                    and to_addr
                                                ):
                                                    topic_src = lg["topics"][1].hex()
                                                    src = "0x" + topic_src[-40:]
                                                            if src.lower() == to_addr:
                                                                val = int(lg.get("data", "0x0"), 16)
                                                                amount_out_est = val
                                                                break
                                            # Fallback via balance delta
                                            if amount_out_est is None and (self.wallet.address):
                                                try:
                                                    bn = rcpt.get("blockNumber")
                                                    addr = self.wallet.address
                                                    bal_before = self.wallet.w3.eth.get_balance(addr, bn - 1)
                                                    bal_after = self.wallet.w3.eth.get_balance(addr, bn)
                                                    gas = int(gas_spent) if gas_spent else 0
                                                    delta = int(bal_after) - int(bal_before)
                                                    recv = delta + gas
                                                    if recv > 0:
                                                        amount_out_est = recv
                                                except Exception as __e:
                                                    logger.debug("Balance delta fallback failed: {}", __e)
                                            # Fallback via Alchemy traces
                                            if (
                                                amount_out_est is None
                                                and self.settings.alchemy_base_url
                                                and self.settings.alchemy_api_key
                                                and self.wallet.address
                                            ):
                                                rpc_url = f"{self.settings.alchemy_base_url.rstrip('/')}/{self.settings.alchemy_api_key}"
                                                traced = trace_native_received(rpc_url, tx_hash, self.wallet.address)
                                                if traced:
                                                    amount_out_est = traced
                                except Exception as _e:
                                    logger.debug("Receipt parsing failed: {}", _e)
                                if amount_out_est is None:
                                    amount_out_est = min_out

                        except Exception as e:
                            status = "failed"
                            err = str(e)
                            logger.exception("Execution failed: {}", e)

                    elif (not decoded_is_v2) and method in ("exactInputSingle",):
                        try:
                            router_addr = Web3.to_checksum_address(rec.dex)
                            router = self.wallet.w3.eth.contract(address=router_addr, abi=self.v3_abi)
                            quoter_addr = self.settings.dex_routers.v3_quoters.get(self.settings.evm_chain_id)
                            if not quoter_addr:
                                status = "skipped"
                                err = "No V3 quoter configured for chain"
                                raise Exception(err)
                            quoter = self.wallet.w3.eth.contract(address=Web3.to_checksum_address(quoter_addr), abi=self.v3_quoter_abi)

                            p = params.get("params") if isinstance(params, dict) else None
                            token_in = Web3.to_checksum_address(p.get("tokenIn"))
                            token_out = Web3.to_checksum_address(p.get("tokenOut"))
                            fee = int(p.get("fee"))
                            if not tokens_ok([token_in, token_out]):
                                status = "skipped"
                                err = "Tokens not allowed by policy"
                                raise Exception(err)

                            observed_amount_in = int(p.get("amountIn"))
                            use_amount_in = int(observed_amount_in * max(0.0, eff_copy_ratio))

                            recipient = self.wallet.address or "0x0000000000000000000000000000000000000000"
                            deadline = int(time.time()) + int(self.settings.tx_deadline_seconds)

                            min_out = compute_min_out_single(quoter, token_in, token_out, fee, use_amount_in, eff_slippage_bps)

                            native_value = 0
                            # If tokenIn is wrapped native, we can pay in ETH
                            wrapped_native = self.settings.dex_routers.native_wrapped.get(self.settings.evm_chain_id)
                            if wrapped_native and token_in.lower() == wrapped_native.lower():
                                native_value = use_amount_in
                                if eff_max_native:
                                    native_value = min(native_value, int(eff_max_native))
                                    use_amount_in = native_value

                            # Approve tokenIn if not paying native
                            if native_value == 0 and not self.settings.dry_run:
                                erc20 = self.wallet.erc20(token_in)
                                allowance = int(erc20.functions.allowance(self.wallet.address, router_addr).call())
                                if allowance < use_amount_in:
                                    logger.info("Approving router {} for {} wei of {} (V3)", router_addr, use_amount_in, token_in)
                                    tx = erc20.functions.approve(router_addr, use_amount_in).build_transaction({"from": self.wallet.address})
                                    tx_hash = self.wallet.send_tx(tx)
                                    logger.info("Approve tx: {}", tx_hash)

                            plan = V3SinglePlan(
                                router=router_addr,
                                token_in=token_in,
                                token_out=token_out,
                                fee=fee,
                                amount_in=use_amount_in,
                                min_out=min_out,
                                recipient=recipient,
                                deadline=deadline,
                                value=native_value,
                            )

                            # Try aggregator first if configured
                            amount_out_est = None
                            is_native_in = native_value > 0
                            agg_txh, agg_buy = self._try_aggregator(token_in, token_out, use_amount_in, is_native_in, eff_slippage_bps)
                            skip_router = False
                            if agg_txh is not None:
                                tx_hash = agg_txh
                                status = "success"
                                amount_out_est = agg_buy
                                skip_router = True
                            elif agg_buy is not None:
                                status = "skipped"
                                amount_out_est = agg_buy
                                skip_router = True

                            if not skip_router:
                                tx = build_exact_input_single(router, plan)
                                if self.settings.dry_run:
                                    status = "skipped"
                                else:
                                    tx.setdefault("from", self.wallet.address)
                                    if plan.value:
                                        tx["value"] = plan.value
                                    if self.settings.max_fee_gwei is not None:
                                        tx["maxFeePerGas"] = self.wallet.w3.to_wei(self.settings.max_fee_gwei, "gwei")
                                    if self.settings.max_priority_fee_gwei is not None:
                                        tx["maxPriorityFeePerGas"] = self.wallet.w3.to_wei(self.settings.max_priority_fee_gwei, "gwei")
                                tx_hash = self.wallet.send_tx(tx)
                                status = "success"
                                try:
                                    rcpt = self.wallet.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                                    if rcpt and rcpt.get("status") == 1:
                                        gas_used = rcpt.get("gasUsed")
                                        eff = rcpt.get("effectiveGasPrice")
                                        if gas_used is not None and eff is not None:
                                            gas_spent = str(int(gas_used) * int(eff))
                                        if rec.token_out:
                                            transfer_sig = self.wallet.w3.keccak(text="Transfer(address,address,uint256)").hex()
                                            to_addr = (self.wallet.address or "").lower()
                                            for lg in rcpt.get("logs", []):
                                                if (
                                                    lg.get("address", "").lower() == rec.token_out.lower()
                                                    and lg.get("topics", [])[0].hex() == transfer_sig
                                                    and len(lg.get("topics", [])) >= 3
                                                    and to_addr
                                                ):
                                                    topic_to = lg["topics"][2].hex()
                                                    addr = "0x" + topic_to[-40:]
                                                        if addr.lower() == to_addr:
                                                            val = int(lg.get("data", "0x0"), 16)
                                                            amount_out_est = val
                                                            break
                                        else:
                                            wrapped = self.settings.dex_routers.native_wrapped.get(self.settings.evm_chain_id)
                                            if wrapped:
                                                withdraw_sig = self.wallet.w3.keccak(text="Withdrawal(address,uint256)").hex()
                                                to_addr = (self.wallet.address or "").lower()
                                            for lg in rcpt.get("logs", []):
                                                if (
                                                    lg.get("address", "").lower() == wrapped.lower()
                                                    and lg.get("topics", [])[0].hex() == withdraw_sig
                                                    and len(lg.get("topics", [])) >= 2
                                                    and to_addr
                                                ):
                                                    topic_src = lg["topics"][1].hex()
                                                    src = "0x" + topic_src[-40:]
                                                            if src.lower() == to_addr:
                                                                val = int(lg.get("data", "0x0"), 16)
                                                                amount_out_est = val
                                                                break
                                            # Fallback via balance delta
                                            if amount_out_est is None and (self.wallet.address):
                                                try:
                                                    bn = rcpt.get("blockNumber")
                                                    addr = self.wallet.address
                                                    bal_before = self.wallet.w3.eth.get_balance(addr, bn - 1)
                                                    bal_after = self.wallet.w3.eth.get_balance(addr, bn)
                                                    gas = int(gas_spent) if gas_spent else 0
                                                    delta = int(bal_after) - int(bal_before)
                                                    recv = delta + gas
                                                    if recv > 0:
                                                        amount_out_est = recv
                                                except Exception as __e:
                                                    logger.debug("Balance delta fallback failed: {}", __e)
                                            if (
                                                amount_out_est is None
                                                and self.settings.alchemy_base_url
                                                and self.settings.alchemy_api_key
                                                and self.wallet.address
                                            ):
                                                rpc_url = f"{self.settings.alchemy_base_url.rstrip('/')}/{self.settings.alchemy_api_key}"
                                                traced = trace_native_received(rpc_url, tx_hash, self.wallet.address)
                                                if traced:
                                                    amount_out_est = traced
                                except Exception as _e:
                                    logger.debug("Receipt parsing failed: {}", _e)
                                if amount_out_est is None:
                                    amount_out_est = min_out

                        except Exception as e:
                            status = "failed"
                            err = str(e)
                            logger.exception("Execution failed (V3): {}", e)

                    else:
                        status = "skipped"
                        err = f"Unsupported method: {method}"

                    # aggregator helper now available as instance method

                    exec_rec = ExecutedTrade(
                        observed_trade_id=rec.id,
                        status=status,
                        tx_hash=tx_hash,
                        gas_spent_wei=gas_spent,
                        error=err,
                        token_in=rec.token_in,
                        token_out=rec.token_out,
                        amount_in_wei=rec.amount_in_wei,
                        amount_out_wei=str(amount_out_est) if 'amount_out_est' in locals() and amount_out_est is not None else None,
                    )
                    rec.processed = True
                    # If we executed successfully and have token addresses, try to capture USD values
                    if exec_rec.status in ("success", "skipped"):
                        try:
                            # Basic pricing snapshot; may be None
                            price_in = get_token_price_usd(self.settings.evm_chain_id, exec_rec.token_in)
                            price_out = get_token_price_usd(self.settings.evm_chain_id, exec_rec.token_out)
                            if exec_rec.amount_in_wei and price_in is not None:
                                exec_rec.amount_in_usd = (int(exec_rec.amount_in_wei) / 1e18) * price_in
                            if exec_rec.amount_out_wei and price_out is not None:
                                exec_rec.amount_out_usd = (int(exec_rec.amount_out_wei) / 1e18) * price_out
                            if exec_rec.amount_in_usd is not None and exec_rec.amount_out_usd is not None:
                                exec_rec.pnl_usd = exec_rec.amount_out_usd - exec_rec.amount_in_usd
                        except Exception as _e:
                            logger.debug("Pricing failed: {}", _e)
                    s.add(exec_rec)
            except KeyboardInterrupt:
                logger.info("Executor interrupted; shutting down.")
                break
            except Exception as e:
                logger.exception("Executor error: {}", e)
                time.sleep(2.0)
