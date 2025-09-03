from __future__ import annotations

import base64
import time
from dataclasses import dataclass

from loguru import logger
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from sqlalchemy import select

from trade_clone_engine.aggregators import jupiter
from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import ExecutedTrade, ObservedTrade, session_scope


@dataclass
class SolanaExecutor:
    settings: AppSettings
    client: Client
    keypair: Keypair | None
    pubkey: Pubkey | None

    @classmethod
    def create(cls, settings: AppSettings) -> SolanaExecutor:
        client = Client(settings.sol_rpc_url)
        kp = None
        pk = None
        if settings.sol_executor_private_key:
            import base58

            secret = base58.b58decode(settings.sol_executor_private_key)
            kp = Keypair.from_bytes(secret)
            pk = kp.pubkey()
        elif settings.sol_executor_pubkey:
            pk = Pubkey.from_string(settings.sol_executor_pubkey)
        return cls(settings=settings, client=client, keypair=kp, pubkey=pk)

    def run(self, SessionFactory):
        logger.info("Starting Solana executor (dry_run={})", self.settings.dry_run)
        while True:
            try:
                with session_scope(SessionFactory) as s:
                    rec: ObservedTrade | None = (
                        s.execute(
                            select(ObservedTrade)
                            .where(
                                ObservedTrade.processed.is_(False), ObservedTrade.chain == "solana"
                            )
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
                    tx_sig = None
                    err = None

                    try:
                        if not (rec.token_in and rec.token_out and rec.amount_in_wei):
                            status = "skipped"
                            raise Exception("Insufficient data for quote")

                        amount_in = int(rec.amount_in_wei)
                        route = jupiter.get_quote(
                            self.settings.jupiter_quote_url,
                            input_mint=rec.token_in,
                            output_mint=rec.token_out,
                            amount=amount_in,
                            slippage_bps=self.settings.slippage_bps,
                        )
                        if not route:
                            status = "failed"
                            raise Exception("No Jupiter route")

                        if self.settings.dry_run or not self.keypair or not self.pubkey:
                            status = "skipped"
                        else:
                            swap_tx_b64 = jupiter.get_swap_transaction(
                                self.settings.jupiter_swap_url, route, str(self.pubkey)
                            )
                            if not swap_tx_b64:
                                status = "failed"
                                raise Exception("No swap transaction from Jupiter")
                            raw = base64.b64decode(swap_tx_b64)
                            raw_signed = None
                            # Prefer legacy solana-py Transaction if available; otherwise try solders VersionedTransaction
                            try:
                                from solana.transaction import (
                                    Transaction as LegacyTransaction,  # type: ignore
                                )

                                tx = LegacyTransaction.deserialize(raw)
                                tx.sign(self.keypair)
                                raw_signed = tx.serialize()
                            except Exception:
                                try:
                                    from solders.transaction import (
                                        VersionedTransaction,  # type: ignore
                                    )

                                    vtx = VersionedTransaction.from_bytes(raw)
                                    # Reconstruct signed transaction using message + signer
                                    vtx = VersionedTransaction(vtx.message, [self.keypair])
                                    raw_signed = bytes(vtx)
                                except Exception as e2:
                                    raise Exception(
                                        f"Unable to deserialize/sign Jupiter swap tx: {e2}"
                                    ) from e2

                            resp = self.client.send_raw_transaction(
                                raw_signed, opts=TxOpts(skip_confirmation=False)
                            )
                            tx_sig = resp.value
                            status = "success"

                            # Fetch confirmed transaction to get realized amounts
                            tr = self.client.get_transaction(
                                tx_sig, max_supported_transaction_version=0
                            )
                            meta = (tr.get("result") or {}).get("meta") or {}
                            post = meta.get("postTokenBalances") or []
                            pre = meta.get("preTokenBalances") or []
                            amount_out = None
                            for i in range(min(len(pre), len(post))):
                                p = pre[i]
                                q = post[i]
                                if q.get("owner") == str(self.pubkey):
                                    pa = int((p.get("uiTokenAmount") or {}).get("amount") or 0)
                                    qa = int((q.get("uiTokenAmount") or {}).get("amount") or 0)
                                    if qa > pa:
                                        amount_out = qa - pa
                            exec_rec = ExecutedTrade(
                                observed_trade_id=rec.id,
                                status=status,
                                tx_hash=tx_sig,
                                gas_spent_wei=None,
                                error=None,
                                token_in=rec.token_in,
                                token_out=rec.token_out,
                                amount_in_wei=rec.amount_in_wei,
                                amount_out_wei=str(amount_out) if amount_out is not None else None,
                            )
                            rec.processed = True
                            s.add(exec_rec)
                            continue
                    except Exception as e:
                        err = str(e)
                        status = "failed" if status == "skipped" else status

                    exec_rec = ExecutedTrade(
                        observed_trade_id=rec.id,
                        status=status,
                        tx_hash=tx_sig,
                        gas_spent_wei=None,
                        error=err,
                        token_in=rec.token_in,
                        token_out=rec.token_out,
                        amount_in_wei=rec.amount_in_wei,
                        amount_out_wei=None,
                    )
                    rec.processed = True
                    s.add(exec_rec)
            except KeyboardInterrupt:
                logger.info("Solana executor interrupted; shutting down.")
                break
            except Exception as e:
                logger.exception("Solana executor error: {}", e)
                time.sleep(2)
