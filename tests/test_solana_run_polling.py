from __future__ import annotations


def test_solana_run_processes_one_iteration_and_inserts(tmp_path, monkeypatch):
    from trade_clone_engine.chains.solana_watcher import SolanaWatcher
    from trade_clone_engine.config import AppSettings
    from trade_clone_engine.db import (
        Base,
        ObservedTrade,
        make_engine,
        make_session_factory,
        session_scope,
    )

    # Prepare wallets.yaml with one wallet
    owner = "9xQeWvG816bUx9EPm2Tbd2Ykqg3k9uADuZbL9g1z3Q2E"
    wallets_yaml = tmp_path / "wallets.yaml"
    wallets_yaml.write_text(
        """
wallets:
  - chain: solana
    address: "9xQeWvG816bUx9EPm2Tbd2Ykqg3k9uADuZbL9g1z3Q2E"
        """.strip()
    )

    # Temp SQLite
    db_url = f"sqlite+pysqlite:///{tmp_path / 'tce.db'}"
    monkeypatch.setenv("TCE_DATABASE_URL", db_url)

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def get_signatures_for_address(self, addr, limit=100):
            self.calls += 1
            if self.calls == 1:
                return {"result": [{"signature": "sigX"}]}
            # Raise KeyboardInterrupt to stop the while loop on next iteration
            raise KeyboardInterrupt

        def get_transaction(self, sig, max_supported_transaction_version=0):
            mint_in = "So11111111111111111111111111111111111111112"
            pre = [{"owner": owner, "mint": mint_in, "uiTokenAmount": {"amount": "300"}}]
            post = [{"owner": owner, "mint": mint_in, "uiTokenAmount": {"amount": "100"}}]
            return {
                "result": {"slot": 1, "meta": {"preTokenBalances": pre, "postTokenBalances": post}}
            }

    settings = AppSettings(wallets_config=str(wallets_yaml))
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    SessionFactory = make_session_factory(settings.database_url)

    watcher = SolanaWatcher(settings=settings, client=FakeClient())
    watcher.run(SessionFactory)

    with session_scope(SessionFactory) as s:
        rows = s.query(ObservedTrade).all()
        assert len(rows) == 1
        assert rows[0].wallet == owner
        assert rows[0].chain == "solana"


def test_solana_run_no_wallets_returns(monkeypatch):
    from trade_clone_engine.chains.solana_watcher import SolanaWatcher
    from trade_clone_engine.config import AppSettings

    class DummyClient:
        pass

    settings = AppSettings()
    w = SolanaWatcher(settings=settings, client=DummyClient())
    # Force no wallets
    w.wallets = lambda: []  # type: ignore[assignment]
    # Should simply return without raising
    w.run(lambda: None)
