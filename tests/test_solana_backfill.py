from __future__ import annotations


def test_solana_backfill_inserts_observed_trades(tmp_path, monkeypatch):
    from trade_clone_engine.chains.solana_watcher import SolanaWatcher
    from trade_clone_engine.config import AppSettings
    from trade_clone_engine.db import (
        Base,
        ObservedTrade,
        make_engine,
        make_session_factory,
        session_scope,
    )

    # Prepare temp DB
    db_path = tmp_path / "tce.db"
    db_url = f"sqlite+pysqlite:///{db_path}"
    monkeypatch.setenv("TCE_DATABASE_URL", db_url)

    # Wallets file with one Solana wallet
    wallets_yaml = tmp_path / "wallets.yaml"
    owner = "9xQeWvG816bUx9EPm2Tbd2Ykqg3k9uADuZbL9g1z3Q2E"
    wallets_yaml.write_text(
        """
wallets:
  - chain: solana
    address: "9xQeWvG816bUx9EPm2Tbd2Ykqg3k9uADuZbL9g1z3Q2E"
        """.strip()
    )

    # Fake Solana client
    class FakeClient:
        def __init__(self):
            self.calls = []

        def get_signatures_for_address(self, addr, before=None, limit=100):
            self.calls.append(("sigs", addr, before, limit))
            # First page: two signatures; then empty
            if before is None:
                return {"result": [{"signature": "sig1"}, {"signature": "sig2"}]}
            return {"result": []}

        def get_transaction(self, sig, max_supported_transaction_version=0):
            self.calls.append(("tx", sig))
            # Create a simple pre/post delta for the same owner
            mint_in = "So11111111111111111111111111111111111111112"
            mint_out = "Es9vMFrzaCERmJfrF4H2FYxTea7PhYRYrRyYLfnLKz7j"
            if sig == "sig1":
                pre = [{"owner": owner, "mint": mint_in, "uiTokenAmount": {"amount": "200"}}]
                post = [{"owner": owner, "mint": mint_in, "uiTokenAmount": {"amount": "100"}}]
            else:
                pre = [{"owner": owner, "mint": mint_out, "uiTokenAmount": {"amount": "100"}}]
                post = [{"owner": owner, "mint": mint_out, "uiTokenAmount": {"amount": "220"}}]
            return {
                "result": {
                    "slot": 123,
                    "meta": {"preTokenBalances": pre, "postTokenBalances": post},
                }
            }

    settings = AppSettings(wallets_config=str(wallets_yaml))
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    SessionFactory = make_session_factory(settings.database_url)

    watcher = SolanaWatcher(settings=settings, client=FakeClient())
    inserted = watcher.backfill(SessionFactory, pages=1, limit=10)
    assert inserted == 2

    with session_scope(SessionFactory) as s:
        rows = s.query(ObservedTrade).all()
        assert len(rows) == 2
        # Ensure chain and wallet set
        assert all(r.chain == "solana" for r in rows)
        assert all(r.wallet == owner for r in rows)
