from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from loguru import logger
from web3 import Web3
from web3.contract import Contract

from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import ObservedTrade, session_scope


@dataclass
class EvmWatcher:
    settings: AppSettings
    w3: Web3
    v2_router: Optional[Contract]
    v3_router: Optional[Contract]

    @classmethod
    def create(cls, settings: AppSettings) -> "EvmWatcher":
        w3 = Web3(Web3.WebsocketProvider(settings.evm_rpc_ws_url))
        logger.info("Connected to EVM provider: {} (chain id {})", settings.evm_rpc_ws_url, settings.evm_chain_id)

        # Prepare router ABIs for decoding only (address may vary)
        v2_abi = json.loads((Path(__file__).resolve().parent.parent / "abi" / "uniswap_v2_router.json").read_text())
        v3_abi = json.loads((Path(__file__).resolve().parent.parent / "abi" / "uniswap_v3_router.json").read_text())

        # We will create contract instances lazily using tx.to address
        dummy_addr = "0x0000000000000000000000000000000000000000"
        v2_router = w3.eth.contract(address=dummy_addr, abi=v2_abi)
        v3_router = w3.eth.contract(address=dummy_addr, abi=v3_abi)
        return cls(settings=settings, w3=w3, v2_router=v2_router, v3_router=v3_router)

    def is_known_dex(self, address: Optional[str]) -> bool:
        if not address:
            return False
        addr = Web3.to_checksum_address(address)
        candidates = [Web3.to_checksum_address(a) for a in self.settings.dex_routers.evm.get(self.settings.evm_chain_id, [])]
        return addr in candidates

    def decode_method(self, to_addr: str, input_data: bytes) -> tuple[str | None, dict | None]:
        # Attempt Uniswap v2
        try:
            func, params = self.v2_router.decode_function_input(input_data)
            return func.fn_name, params
        except Exception:
            pass
        # Attempt Uniswap v3
        try:
            func, params = self.v3_router.decode_function_input(input_data)
            return func.fn_name, params
        except Exception:
            pass
        return None, None

    def follow_addresses(self) -> set[str]:
        return set(a.lower() for a in self.settings.wallets_to_follow(chain="evm"))

    def run(self, SessionFactory):
        logger.info("Starting EVM watcher on chain {}", self.settings.evm_chain_id)
        followed = self.follow_addresses()
        if not followed:
            logger.warning("No wallets configured to follow. Update config/wallets.yaml")

        last_block = self.w3.eth.block_number
        logger.info("Initial block: {}", last_block)

        while True:
            try:
                latest = self.w3.eth.block_number
                if latest <= last_block:
                    time.sleep(self.settings.block_poll_interval_sec)
                    continue

                for bn in range(last_block + 1, latest + 1):
                    block = self.w3.eth.get_block(bn, full_transactions=True)
                    txs: Iterable = block.transactions or []
                    for tx in txs:
                        from_addr = (tx["from"] or "").lower()
                        to_addr = (tx.get("to") or "").lower()
                        input_data: bytes = tx.get("input", b"")

                        if from_addr in followed or to_addr in followed:
                            # Potential internal transfer or approval; focus on DEX swaps
                            if not self.is_known_dex(to_addr):
                                continue

                            method, params = (None, None)
                            if input_data and input_data != "0x":
                                try:
                                    method, params = self.decode_method(to_addr, input_data)
                                except Exception as e:
                                    logger.debug("decode error: {}", e)

                            # Determine token_in/out and amounts across V2/V3 shapes
                            token_in = None
                            token_out = None
                            amount_in = None
                            min_out = None

                            if params:
                                # V2 path-based
                                if isinstance(params.get("path"), (list, tuple)) and params.get("path"):
                                    token_in = str(params.get("path")[0])
                                    token_out = str(params.get("path")[-1])
                                # V3 exactInputSingle tuple
                                if isinstance(params.get("params"), dict):
                                    p = params.get("params")
                                    token_in = str(p.get("tokenIn")) if p.get("tokenIn") else token_in
                                    token_out = str(p.get("tokenOut")) if p.get("tokenOut") else token_out
                                    amount_in = str(p.get("amountIn")) if p.get("amountIn") is not None else amount_in
                                    min_out = str(p.get("amountOutMinimum")) if p.get("amountOutMinimum") is not None else min_out

                                amount_in = str(params.get("amountIn")) if amount_in is None and params.get("amountIn") is not None else amount_in
                                min_out = str(params.get("amountOutMin")) if min_out is None and params.get("amountOutMin") is not None else min_out

                            if amount_in is None:
                                amount_in = str(tx.get("value")) if tx.get("value") else None

                            with session_scope(SessionFactory) as s:
                                rec = ObservedTrade(
                                    chain="evm",
                                    tx_hash=tx["hash"].hex() if hasattr(tx["hash"], "hex") else str(tx["hash"]),
                                    block_number=bn,
                                    wallet=from_addr,
                                    dex=to_addr,
                                    method=method,
                                    token_in=token_in,
                                    token_out=token_out,
                                    amount_in_wei=amount_in,
                                    min_out_wei=min_out,
                                    raw_input=input_data if isinstance(input_data, str) else input_data.hex(),
                                )
                                s.add(rec)
                            logger.info("Observed trade: {} {} {} -> {} (method: {})", rec.wallet, rec.dex, rec.token_in, rec.token_out, rec.method)

                last_block = latest
            except KeyboardInterrupt:
                logger.info("Watcher interrupted; shutting down.")
                break
            except Exception as e:
                logger.exception("Watcher error: {}", e)
                time.sleep(self.settings.block_poll_interval_sec)
