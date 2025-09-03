from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import Base


def test_settings_load():
    s = AppSettings()
    assert s is not None


def test_db_models_present():
    assert hasattr(Base, "metadata")


def test_wallet_overrides_shape():
    s = AppSettings()
    overrides = s.wallet_overrides()
    assert isinstance(overrides, dict)
