from fastapi.testclient import TestClient


def test_empty_env_coercion(monkeypatch):
    from trade_clone_engine.config import AppSettings

    monkeypatch.setenv("TCE_MAX_PRIORITY_FEE_GWEI", "")
    monkeypatch.setenv("TCE_MAX_FEE_GWEI", "")
    monkeypatch.setenv("TCE_DUNE_QUERY_ID", "")
    s = AppSettings()
    assert s.max_priority_fee_gwei is None
    assert s.max_fee_gwei is None
    assert s.dune_query_id is None


def test_wallets_to_follow_case_sensitive(tmp_path):
    from trade_clone_engine.config import AppSettings

    wallets_yaml = tmp_path / "wallets.yaml"
    wallets_yaml.write_text(
        """
wallets:
  - chain: evm
    address: "0xABcDEF1234567890"
  - chain: solana
    address: "GxhQ5LTFc4dTxAXt7aQ4uSKvr8ev9T2QXE9zWKA3pjFP"
        """.strip()
    )

    s = AppSettings(wallets_config=str(wallets_yaml))
    evm = s.wallets_to_follow(chain="evm")
    sol = s.wallets_to_follow(chain="solana")
    assert evm == ["0xabcdef1234567890"]  # lowercased
    assert sol == ["GxhQ5LTFc4dTxAXt7aQ4uSKvr8ev9T2QXE9zWKA3pjFP"]  # preserved


def test_api_endpoints_with_sqlite(tmp_path, monkeypatch):
    # Use a file-based sqlite for persistence across connections
    db_path = tmp_path / "tce.db"
    db_url = f"sqlite+pysqlite:///{db_path}"
    monkeypatch.setenv("TCE_DATABASE_URL", db_url)

    # Import after setting env so the module picks it up
    from services.api.main import app, settings
    from trade_clone_engine.db import (
        Base,
        ExecutedTrade,
        ObservedTrade,
        make_engine,
        make_session_factory,
        session_scope,
    )

    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    SessionFactory = make_session_factory(settings.database_url)

    # Seed a trade and an execution
    with session_scope(SessionFactory) as s:
        o = ObservedTrade(
            chain="solana",
            tx_hash="abc",
            block_number=1,
            wallet="GxhQ...",
            dex="jupiter",
            method="swap",
            token_in="So11111111111111111111111111111111111111112",
            token_out="Es9vMFrzaCERmJfrF4H2FYxTea7PhYRYrRyYLfnLKz7j",
            amount_in_wei="1000",
            min_out_wei="900",
            raw_input="",
        )
        s.add(o)
        s.flush()
        e = ExecutedTrade(
            observed_trade_id=o.id,
            status="skipped",
            tx_hash=None,
            gas_spent_wei=None,
            error=None,
        )
        s.add(e)

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    r = client.get("/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_observed"] >= 1
    r = client.get("/trades")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    r = client.get("/executions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    r = client.get("/dashboard")
    assert r.status_code in (200, 404)  # 200 if static is included in test env
