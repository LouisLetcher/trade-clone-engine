from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DexRouters(BaseModel):
    # EVM mainnet/testnets: map of chain_id -> list of router addresses
    evm: dict[int, List[str]] = {
        1: [
            # Uniswap V2 & V3 main routers
            "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # V2
            "0xE592427A0AEce92De3Edee1F18E0157C05861564",  # V3
        ],
        137: [  # Polygon
            "0xE592427A0AEce92De3Edee1F18E0157C05861564",  # Uniswap V3
            "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",  # QuickSwap V2 router
            "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",  # SushiSwap V2 router
            "0xA102072A4C07F06EC3B4900FDC4C7B80b6c57429",  # Dfyn V2 router
            "0xC0788A3aD43d79aa53B09c2EaCc313A787d1d607",  # ApeSwap router
        ],
        8453: [  # Base
            "0x2626664c2603336E57B271c5C0b26F421741e481",  # Uniswap V3 Base
        ],
    }

    # Uniswap V3 Quoter addresses per chain
    v3_quoters: dict[int, str] = {
        1: "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",   # Ethereum
        137: "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",  # Polygon
        8453: "0x61fFE014bA17989E743c5F6cB21bF9697530B21e", # Base
    }

    # Wrapped native per chain (WETH)
    native_wrapped: dict[int, str] = {
        1: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",     # WETH9
        137: "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",   # WMATIC
        8453: "0x4200000000000000000000000000000000000006",   # WETH (Base)
    }


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env",), env_prefix="TCE_", extra="allow")

    # Database
    database_url: str = "postgresql+psycopg2://tce:tce@postgres:5432/tce"

    # EVM provider
    evm_rpc_ws_url: str = "ws://localhost:8546"
    evm_chain_id: int = 1

    # Solana
    sol_rpc_url: str = "https://api.mainnet-beta.solana.com"
    sol_executor_private_key: Optional[str] = None  # base58 secret key
    sol_executor_pubkey: Optional[str] = None
    jupiter_quote_url: str = "https://quote-api.jup.ag/v6/quote"
    jupiter_swap_url: str = "https://quote-api.jup.ag/v6/swap"
    sol_subscribe_logs: bool = False

    # Execution
    dry_run: bool = True
    evm_private_key: Optional[str] = None
    executor_address: Optional[str] = None
    slippage_bps: int = 300  # 3%
    copy_ratio: float = 1.0  # fraction of observed input amount
    max_native_in_wei: int = 0  # 0 means no additional cap
    tx_deadline_seconds: int = 600
    max_priority_fee_gwei: Optional[float] = None
    max_fee_gwei: Optional[float] = None

    # Aggregators
    aggregator: Optional[str] = None  # '1inch' | '0x'
    oneinch_base_url: str = "https://api.1inch.dev/swap/v5.2"
    oneinch_api_key: Optional[str] = None
    zeroex_base_url: str = "https://api.0x.org"
    zeroex_base_url_base_chain: str = "https://base.api.0x.org"
    zeroex_base_url_polygon: str = "https://polygon.api.0x.org"
    zeroex_base_url_arbitrum: str = "https://arbitrum.api.0x.org"
    zeroex_base_url_optimism: str = "https://optimism.api.0x.org"

    # Discovery
    dune_api_key: Optional[str] = None
    dune_query_id: Optional[int] = None
    birdeye_api_key: Optional[str] = None
    discover_interval_sec: int = 3600
    discover_top_percent: float = 1.0
    discover_min_trades: int = 10
    nansen_api_key: Optional[str] = None
    nansen_base_url: Optional[str] = None
    nansen_endpoint_path: Optional[str] = None

    # Alchemy (optional for traces/receipts)
    alchemy_api_key: Optional[str] = None
    alchemy_base_url: Optional[str] = None

    # Aggregator per chain (overrides global aggregator). Values: '1inch' | '0x'
    aggregator_chain_1: Optional[str] = None
    aggregator_chain_137: Optional[str] = None
    aggregator_chain_8453: Optional[str] = None

    # Discovery label filters (comma-separated lists)
    discover_allowed_labels: Optional[str] = None
    discover_denied_labels: Optional[str] = None
    discover_chain: Optional[str] = None  # limit discovery to a specific chain, e.g. 'solana' or 'evm'
    discover_once: bool = False  # if true, discovery service runs once and exits
    discover_prune_others: bool = False  # if true and discover_chain set, prune wallets of other chains

    # Config files
    wallets_config: str = "config/wallets.yaml"

    # Dex routers
    dex_routers: DexRouters = DexRouters()

    # Polling
    block_poll_interval_sec: float = 3.0

    # Logging
    log_level: str = "INFO"

    # --- Validators to coerce empty strings in optional envs to None ---
    @field_validator("max_priority_fee_gwei", "max_fee_gwei", "dune_query_id", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        if v == "":
            return None
        return v

    def wallets_to_follow(self, chain: str = "evm") -> List[str]:
        import yaml

        path = Path(self.wallets_config)
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        lst: List[str] = []
        for item in data.get("wallets", []):
            addr = item.get("address")
            item_chain = (item.get("chain") or "evm").lower()
            if addr and item_chain == chain.lower():
                # EVM addresses are case-insensitive; Solana pubkeys are case-sensitive base58
                if chain.lower() == "evm":
                    lst.append(addr.lower())
                else:
                    lst.append(addr)
        return lst

    def wallet_overrides(self) -> Dict[str, dict]:
        import yaml

        path = Path(self.wallets_config)
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text()) or {}
        out: Dict[str, dict] = {}
        for item in data.get("wallets", []):
            raw_addr = (item.get("address") or "")
            # Normalize EVM addresses to lowercase; keep Solana as-is
            addr = raw_addr.lower() if raw_addr.startswith("0x") else raw_addr
            if not addr:
                continue
            cfg = {k: v for k, v in item.items() if k != "address"}
            out[addr] = cfg
        return out
