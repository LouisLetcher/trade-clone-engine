from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from solana.rpc.api import Client
from solana.rpc.websocket_api import connect as ws_connect

from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import ObservedTrade, session_scope


@dataclass
class SolanaWatcher:
    settings: AppSettings
    client: Client

    @classmethod
    def create(cls, settings: AppSettings) -> SolanaWatcher:
        client = Client(settings.sol_rpc_url)
        return cls(settings=settings, client=client)

    def wallets(self) -> list[str]:
        return self.settings.wallets_to_follow(chain="solana")

    def run(self, SessionFactory):
        logger.info("Starting Solana watcher: {}", self.settings.sol_rpc_url)
        wallets = self.wallets()
        if not wallets:
            logger.warning("No Solana wallets configured to follow.")
            return
        # Simple polling of recent signatures; optionally subscribe to logs for near real-time
        seen = set()
        while True:
            try:
                for w in wallets:
                    sigs = self.client.get_signatures_for_address(w, limit=20)["result"]
                    for s in sigs:
                        sig = s["signature"]
                        if sig in seen:
                            continue
                        seen.add(sig)
                        txr = self.client.get_transaction(sig, max_supported_transaction_version=0)
                        res = txr.get("result")
                        if not res:
                            continue
                        meta = res.get("meta") or {}
                        pre = meta.get("preTokenBalances") or []
                        post = meta.get("postTokenBalances") or []
                        # Decode net token delta for the wallet precisely using token balances
                        amount_in = None
                        amount_out = None
                        mint_in = None
                        mint_out = None
                        for i in range(min(len(pre), len(post))):
                            p = pre[i]
                            q = post[i]
                            if p.get("owner") != w:
                                continue
                            pa = int((p.get("uiTokenAmount") or {}).get("amount") or 0)
                            qa = int((q.get("uiTokenAmount") or {}).get("amount") or 0)
                            if pa > qa:
                                amount_in = pa - qa
                                mint_in = p.get("mint")
                            elif qa > pa:
                                amount_out = qa - pa
                                mint_out = p.get("mint")
                        # Also consider SOL changes
                        # Store observed record
                        with session_scope(SessionFactory) as sdb:
                            rec = ObservedTrade(
                                chain="solana",
                                tx_hash=sig,
                                block_number=int(res.get("slot") or 0),
                                wallet=w,
                                dex="jupiter?",
                                method="swap",
                                token_in=mint_in,
                                token_out=mint_out,
                                amount_in_wei=str(amount_in) if amount_in is not None else None,
                                min_out_wei=str(amount_out) if amount_out is not None else None,
                                raw_input="",
                            )
                            sdb.add(rec)
                        logger.info("Observed Solana trade: {} {} -> {}", w, mint_in, mint_out)
            except KeyboardInterrupt:
                logger.info("Solana watcher interrupted; shutting down.")
                break
            except Exception as e:
                logger.exception("Solana watcher error: {}", e)
                import time

                time.sleep(2)

    async def run_subscribe(self, SessionFactory):
        # Optional logs subscription for Jupiter/Raydium program logs (improves latency)
        wallets = set(self.wallets())
        if not wallets:
            logger.warning("No Solana wallets configured; subscription aborted.")
            return
        async with ws_connect(
            self.settings.sol_rpc_url.replace("https://", "wss://").replace("http://", "ws://")
        ) as websocket:
            # Subscribe once per wallet using solders Mentions filter (expects a single Pubkey)
            subs = []
            errors = []
            try:
                from solders.pubkey import Pubkey as SPubkey  # type: ignore
                from solders.rpc.config import RpcTransactionLogsFilterMentions  # type: ignore

                for w in wallets:
                    try:
                        filt = RpcTransactionLogsFilterMentions(SPubkey.from_string(w))
                        sub = await websocket.logs_subscribe(filter_=filt)
                        subs.append(sub)
                    except Exception as e:  # noqa: BLE001
                        errors.append((w, e))
            except Exception as e:
                errors.append(("import", e))

            if not subs:
                logger.error("Failed to establish any logs subscription: {}", errors)
                return
            logger.info("Solana logs subscriptions established for {} wallet(s)", len(subs))
            try:
                while True:
                    msg = await websocket.recv()
                    value = (msg.result or {}).get("value") if hasattr(msg, "result") else None
                    if not value:
                        continue
                    sig = value.get("signature")
                    if not sig:
                        continue
                    # Filter to our wallets if mentions are present
                    if (
                        value.get("mentions")
                        and wallets
                        and not any(m in wallets for m in (value.get("mentions") or []))
                    ):
                        continue
                    txr = self.client.get_transaction(sig, max_supported_transaction_version=0)
                    res = txr.get("result")
                    if not res:
                        continue
                    meta = res.get("meta") or {}
                    pre = meta.get("preTokenBalances") or []
                    post = meta.get("postTokenBalances") or []
                    w = None
                    amount_in = amount_out = None
                    mint_in = mint_out = None
                    # Pick any wallet from mentions as owner
                    for bal in post:
                        if bal.get("owner") in wallets:
                            w = bal.get("owner")
                            break
                    if not w:
                        continue
                    for i in range(min(len(pre), len(post))):
                        p = pre[i]
                        q = post[i]
                        if p.get("owner") != w:
                            continue
                        pa = int((p.get("uiTokenAmount") or {}).get("amount") or 0)
                        qa = int((q.get("uiTokenAmount") or {}).get("amount") or 0)
                        if pa > qa:
                            amount_in = pa - qa
                            mint_in = p.get("mint")
                        elif qa > pa:
                            amount_out = qa - pa
                            mint_out = p.get("mint")
                    with session_scope(SessionFactory) as sdb:
                        rec = ObservedTrade(
                            chain="solana",
                            tx_hash=sig,
                            block_number=int(res.get("slot") or 0),
                            wallet=w,
                            dex="jupiter?",
                            method="swap",
                            token_in=mint_in,
                            token_out=mint_out,
                            amount_in_wei=str(amount_in) if amount_in is not None else None,
                            min_out_wei=str(amount_out) if amount_out is not None else None,
                            raw_input="",
                        )
                        sdb.add(rec)
                    logger.info("Observed Solana trade (sub): {} {} -> {}", w, mint_in, mint_out)
            except Exception as e:
                logger.exception("Solana subscription error: {}", e)
