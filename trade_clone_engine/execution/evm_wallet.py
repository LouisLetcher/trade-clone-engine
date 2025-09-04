from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from eth_account import Account
from loguru import logger
from web3 import Web3


def _load_abi(rel_path: str):
    path = Path(__file__).resolve().parent.parent / "abi" / rel_path
    return json.loads(path.read_text())


ERC20_ABI = _load_abi("erc20.json")
UNI_V2_ABI = _load_abi("uniswap_v2_router.json")


@dataclass
class EvmWallet:
    w3: Web3
    chain_id: int
    private_key: str | None
    address: str | None

    @classmethod
    def create(
        cls, rpc_url: str, chain_id: int, private_key: str | None, explicit_address: str | None
    ):
        if rpc_url.startswith("ws"):
            wsprov = getattr(Web3, "WebsocketProvider", None)
            if wsprov is None:
                raise RuntimeError(
                    "WebsocketProvider not available in this web3 build. Use an HTTP RPC URL or install web3 with WS support."
                )
            w3 = Web3(wsprov(rpc_url))
        else:
            hpprov = getattr(Web3, "HTTPProvider", None)
            if hpprov is None:
                from web3.providers.rpc import HTTPProvider as _HTTPProvider  # type: ignore

                hpprov = _HTTPProvider
            w3 = Web3(hpprov(rpc_url))
        addr = explicit_address
        if private_key and not addr:
            addr = Account.from_key(private_key).address
        logger.info("Executor connected to EVM provider: {} (chain id {})", rpc_url, chain_id)
        if addr:
            logger.info("Executor address: {}", addr)
        return cls(w3=w3, chain_id=chain_id, private_key=private_key, address=addr)

    def erc20(self, token_addr: str):
        return self.w3.eth.contract(address=Web3.to_checksum_address(token_addr), abi=ERC20_ABI)

    def router_v2(self, router_addr: str):
        return self.w3.eth.contract(address=Web3.to_checksum_address(router_addr), abi=UNI_V2_ABI)

    def send_tx(self, tx: dict) -> str:
        assert self.private_key, "Private key required for sending transactions"
        assert self.address, "Executor address required"
        # Populate common fields
        tx.setdefault("chainId", self.chain_id)
        if "nonce" not in tx:
            tx["nonce"] = self.w3.eth.get_transaction_count(self.address)
        # Fill gas if not provided
        if "gas" not in tx:
            tx["gas"] = self.w3.eth.estimate_gas({**tx, "from": self.address})
        if "maxFeePerGas" not in tx and "gasPrice" not in tx:
            # EIP-1559 defaults
            latest = self.w3.eth.gas_price
            tx["maxFeePerGas"] = latest * 2
            tx["maxPriorityFeePerGas"] = self.w3.to_wei(2, "gwei")
        signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return tx_hash.hex()
