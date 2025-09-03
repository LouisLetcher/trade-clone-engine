from __future__ import annotations

import time
from pathlib import Path

import yaml
from loguru import logger

from trade_clone_engine.config import AppSettings
from trade_clone_engine.discovery.sources import (
    BirdeyeSource,
    DuneSource,
    GMGNSource,
    NansenSource,
    rank_wallets,
)


def load_wallets_yaml(path: Path) -> dict:
    if not path.exists():
        return {"wallets": []}
    return yaml.safe_load(path.read_text()) or {"wallets": []}


def save_wallets_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def upsert_wallet(wallets: list[dict], item: dict) -> None:
    for w in wallets:
        if w.get("address", "").lower() == item.get("address", "").lower() and (w.get("chain") or "evm").lower() == (item.get("chain") or "evm").lower():
            # Update notes/overrides if present, keep existing risk unless missing
            for k, v in item.items():
                if k not in ("address",) and v is not None and (k not in w or w[k] in (None, "")):
                    w[k] = v
            return
    wallets.append(item)


def run_discovery_once(settings: AppSettings):
    dune = None
    if settings.__dict__.get("dune_api_key"):
        dune = DuneSource(api_key=settings.__dict__["dune_api_key"], query_id=settings.__dict__.get("dune_query_id"))
    birdeye = None
    if settings.__dict__.get("birdeye_api_key"):
        birdeye = BirdeyeSource(api_key=settings.__dict__["birdeye_api_key"])
    gmgn = GMGNSource()
    nansen = None
    if settings.__dict__.get("nansen_api_key"):
        nansen = NansenSource(
            api_key=settings.__dict__["nansen_api_key"],
            base_url=(settings.__dict__.get("nansen_base_url") or "https://api.nansen.ai/api/v1"),
            endpoint_path=(
                settings.__dict__.get("nansen_endpoint_path")
                or "smart-money/top-traders?timeRange=7d"
            ),
        )

    candidates = []
    if dune:
        candidates.extend(dune.top_wallets(limit=500))
    if birdeye:
        candidates.extend(birdeye.top_wallets(limit=500))
    # GMGN is optional/public; may fail if rate-limited
    candidates.extend(gmgn.top_wallets(limit=200))
    if nansen:
        candidates.extend(nansen.top_wallets(limit=500))

    # Label filters
    allow_csv = (settings.__dict__.get("discover_allowed_labels") or "").strip()
    deny_csv = (settings.__dict__.get("discover_denied_labels") or "").strip()
    allow = set([x.strip().lower() for x in allow_csv.split(",") if x.strip()])
    deny = set([x.strip().lower() for x in deny_csv.split(",") if x.strip()])

    def label_ok(w: dict) -> bool:
        labs = [str(x).lower() for x in (w.get("labels") or [])]
        if deny and any(lab in deny for lab in labs):
            return False
        return not (allow and not any(lab in allow for lab in labs))

    # Optional chain filter
    only_chain = (settings.__dict__.get("discover_chain") or "").strip().lower()
    filtered = [w for w in candidates if label_ok(w) and (not only_chain or str(w.get("chain","")) == only_chain)]

    top = rank_wallets(
        filtered,
        min_trades=settings.__dict__.get("discover_min_trades", 10),
        top_percent=float(settings.__dict__.get("discover_top_percent", 1.0)),
    )
    logger.info("Discovered {} top wallets from {} candidates", len(top), len(candidates))

    if not top:
        return

    path = Path(settings.wallets_config)
    data = load_wallets_yaml(path)
    wallets = data.get("wallets", [])

    # Optionally prune existing non-target-chain wallets
    if only_chain and bool(settings.__dict__.get("discover_prune_others", False)):
        wallets = [w for w in wallets if str(w.get("chain") or "").lower() == only_chain]

    # Risk defaults
    default_copy_ratio = settings.copy_ratio
    default_slippage_bps = settings.slippage_bps
    default_max_native = settings.max_native_in_wei

    for w in top:
        item = {
            "chain": w.get("chain", "evm"),
            "address": w["address"],
            "notes": f"discovered pnl=${w.get('pnl_usd', 0.0):.2f} win={w.get('win_rate',0.0):.2f}",
            "copy_ratio": default_copy_ratio,
            "slippage_bps": default_slippage_bps,
            "max_native_in_wei": default_max_native,
            "allowed_tokens": [],
            "denied_tokens": [],
        }
        upsert_wallet(wallets, item)

    data["wallets"] = wallets
    save_wallets_yaml(path, data)
    logger.info("Updated {} with {} wallets", path, len(wallets))


def main_loop():
    settings = AppSettings()
    interval = int(settings.__dict__.get("discover_interval_sec", 3600))
    while True:
        try:
            run_discovery_once(settings)
        except Exception as e:
            logger.exception("Discovery run failed: {}", e)
        time.sleep(interval)
