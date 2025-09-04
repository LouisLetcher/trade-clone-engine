from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests
from loguru import logger

WalletRec = dict[str, Any]


@dataclass
class DuneSource:
    api_key: str
    base_url: str = "https://api.dune.com/api/v1"
    query_id: int | None = None

    def top_wallets(self, limit: int = 100) -> list[WalletRec]:
        if not self.query_id:
            logger.warning("DuneSource: query_id not set; skipping")
            return []
        headers = {"X-DUNE-API-KEY": self.api_key}
        url = f"{self.base_url}/query/{self.query_id}/results"
        r = requests.get(url, headers=headers, timeout=30)
        if not r.ok:
            logger.warning("DuneSource error: {}", r.text)
            return []
        data = r.json() or {}
        rows = data.get("result", {}).get("rows", [])
        out: list[WalletRec] = []
        for row in rows[:limit]:
            raw = row.get("wallet") or row.get("address") or ""
            addr = raw.lower() if raw.startswith("0x") else raw
            if not addr:
                continue
            out.append(
                {
                    "address": addr,
                    "chain": "evm",
                    "pnl_usd": float(row.get("realized_pnl_usd") or 0.0),
                    "win_rate": float(row.get("win_rate") or 0.0),
                    "trades": int(row.get("trades") or 0),
                }
            )
        return out


@dataclass
class BirdeyeSource:
    api_key: str
    base_url: str = "https://public-api.birdeye.so"

    def top_wallets(self, limit: int = 100) -> list[WalletRec]:
        # Placeholder: Birdeye may not expose direct top traders; this is a scaffold.
        headers = {"x-api-key": self.api_key, "accept": "application/json"}
        url = f"{self.base_url}/defi/wallet/ranking"
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if not r.ok:
                logger.warning("Birdeye error: {}", r.text)
                return []
            rows = r.json().get("data", [])
            out: list[WalletRec] = []
            for row in rows[:limit]:
                raw = row.get("address") or ""
                addr = raw.lower() if raw.startswith("0x") else raw
                if not addr:
                    continue
                out.append(
                    {
                        "address": addr,
                        "chain": "solana",
                        "pnl_usd": float(row.get("pnl_usd") or 0.0),
                        "win_rate": float(row.get("win_rate") or 0.0),
                        "trades": int(row.get("trades") or 0),
                    }
                )
            return out
        except Exception as e:
            logger.warning("Birdeye request failed: {}", e)
            return []


@dataclass
class GMGNSource:
    api_key: str | None = None
    base_url: str = "https://gmgn.ai/api"

    def top_wallets(self, limit: int = 100) -> list[WalletRec]:
        # Placeholder implementation; endpoint depends on GMGN plan.
        try:
            r = requests.get(f"{self.base_url}/solana/traders/top", timeout=20)
            if not r.ok:
                logger.warning("GMGN error: {}", r.text)
                return []
            rows = r.json().get("data", [])
            out: list[WalletRec] = []
            for row in rows[:limit]:
                raw = row.get("address") or ""
                addr = raw.lower() if raw.startswith("0x") else raw
                if not addr:
                    continue
                out.append(
                    {
                        "address": addr,
                        "chain": "solana",
                        "pnl_usd": float(row.get("pnl_usd") or 0.0),
                        "win_rate": float(row.get("win_rate") or 0.0),
                        "trades": int(row.get("trades") or 0),
                    }
                )
            return out
        except Exception as e:
            logger.warning("GMGN request failed: {}", e)
            return []


@dataclass
class NansenSource:
    api_key: str
    base_url: str = "https://api.nansen.ai"
    endpoint_path: str = "smart-money/top-traders"

    def _extract_addresses_generic(self, obj: Any) -> list[str]:
        addrs: set[str] = set()
        address_like_keys = {
            "address",
            "wallet",
            "walletAddress",
            "owner",
            "buyer",
            "seller",
            "from",
            "to",
            "fromAddress",
            "toAddress",
        }

        def is_evm(s: str) -> bool:
            return isinstance(s, str) and s.startswith("0x") and len(s) == 42

        def is_solana(s: str) -> bool:
            if not isinstance(s, str):
                return False
            # Fast check: base58 charset subset and typical length 32-44
            if not (32 <= len(s) <= 44):
                return False
            return all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in s)

        def walk(x: Any):
            if isinstance(x, dict):
                for k, v in x.items():
                    if (
                        k in address_like_keys
                        and isinstance(v, str)
                        and (is_evm(v) or is_solana(v))
                    ):
                        addrs.add(v)
                    walk(v)
            elif isinstance(x, list):
                for it in x:
                    walk(it)

        walk(obj)
        return list(addrs)

    def top_wallets(self, limit: int = 100) -> list[WalletRec]:
        headers = {
            "accept": "application/json",
            "NANSEN-API-KEY": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "apiKey": self.api_key,
        }
        try:
            base = (self.base_url or "https://api.nansen.ai/api/v1").rstrip("/")
            path = (self.endpoint_path or "smart-money/top-traders").lstrip("/")
            url = f"{base}/{path}"

            # Use POST for Smart Money endpoints that require a request body
            if path.startswith("smart-money/dex-trades") or path.startswith("smart-money/dcas"):
                discover_chain = (os.getenv("TCE_DISCOVER_CHAIN") or "").strip().lower()
                chains_env = (os.getenv("TCE_NANSEN_SM_CHAINS") or "").strip()
                if chains_env:
                    chains = [c.strip() for c in chains_env.split(",") if c.strip()]
                elif discover_chain == "solana":
                    chains = ["solana"]
                else:
                    chains = ["ethereum"]
                include_labels = [
                    x.strip()
                    for x in (os.getenv("TCE_DISCOVER_ALLOWED_LABELS") or "").split(",")
                    if x.strip()
                ]
                exclude_labels = [
                    x.strip()
                    for x in (os.getenv("TCE_DISCOVER_DENIED_LABELS") or "").split(",")
                    if x.strip()
                ]
                per_page = int(os.getenv("TCE_NANSEN_PER_PAGE") or 50)
                body: dict[str, Any] = {"pagination": {"page": 1, "per_page": per_page}}
                if path.startswith("smart-money/dex-trades"):
                    body["chains"] = chains
                filters: dict[str, Any] = {}
                if include_labels:
                    filters["include_smart_money_labels"] = include_labels
                if exclude_labels:
                    filters["exclude_smart_money_labels"] = exclude_labels
                if filters:
                    body["filters"] = filters
                r = requests.post(url, headers=headers, json=body, timeout=30)
            else:
                r = requests.get(url, headers=headers, timeout=20)
            if not r.ok:
                logger.warning("Nansen error: {} => {}", url, r.text)
                return []
            payload = r.json() or {}
            out: list[WalletRec] = []

            # Try structured rows first
            rows = payload.get("data") or payload.get("items") or payload.get("results") or []
            if isinstance(rows, list) and rows:
                for row in rows:
                    # Flexible field extraction (supports dex-trades/dcas via trader_address)
                    raw = (
                        row.get("trader_address")
                        or row.get("address")
                        or row.get("walletAddress")
                        or row.get("wallet")
                        or ""
                    )
                    addr = raw.lower() if isinstance(raw, str) and raw.startswith("0x") else raw
                    if not addr:
                        continue
                    labels = []
                    raw_labels = row.get("labels") or row.get("tags") or []
                    for lab in raw_labels:
                        if isinstance(lab, str):
                            labels.append(lab)
                        elif isinstance(lab, dict):
                            name = lab.get("name") or lab.get("label")
                            if name:
                                labels.append(name)
                    pnl = (
                        row.get("pnl_usd") or row.get("pnlUsd") or row.get("realizedPnlUsd") or 0.0
                    )
                    win = row.get("win_rate") or row.get("winRate") or 0.0
                    trades = row.get("trades") or row.get("tradeCount") or 0
                    chain = row.get("chain") or (
                        "evm" if isinstance(addr, str) and addr.startswith("0x") else "solana"
                    )
                    out.append(
                        {
                            "address": addr,
                            "chain": str(chain).lower(),
                            "pnl_usd": float(pnl or 0.0),
                            "win_rate": float(win or 0.0),
                            "trades": int(trades or 0),
                            "labels": labels,
                        }
                    )
            else:
                # Generic fallback: recursively extract any address-like strings
                addrs = self._extract_addresses_generic(payload)
                for a in addrs[:limit]:
                    out.append(
                        {
                            "address": a.lower() if a.startswith("0x") else a,
                            "chain": "evm" if a.startswith("0x") else "solana",
                            "pnl_usd": 0.0,
                            "win_rate": 0.0,
                            "trades": 1,  # minimal default to pass filters
                            "labels": [],
                        }
                    )
            # Deduplicate by (address, chain)
            dedup: dict[tuple[str, str], WalletRec] = {}
            for w in out:
                key = (w["address"], w.get("chain", ""))
                dedup[key] = w
            return list(dedup.values())[:limit]
        except Exception as e:
            logger.warning("Nansen request failed: {}", e)
            return []


# Arkham removed: no public API available yet for this purpose.


def rank_wallets(
    candidates: list[WalletRec], min_trades: int = 10, top_percent: float = 1.0
) -> list[WalletRec]:
    # Filter and rank by pnl_usd then win_rate
    filt = [w for w in candidates if int(w.get("trades", 0)) >= min_trades]
    filt.sort(
        key=lambda w: (float(w.get("pnl_usd", 0.0)), float(w.get("win_rate", 0.0))), reverse=True
    )
    if not filt:
        return []
    n = max(1, int(len(filt) * (top_percent / 100.0)))
    return filt[:n]
