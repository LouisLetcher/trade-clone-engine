from loguru import logger

from trade_clone_engine.chains.evm import EvmWatcher
from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import make_session_factory


def main():
    settings = AppSettings()
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=settings.log_level)

    SessionFactory = make_session_factory(settings.database_url)

    # Start only EVM watcher for now
    watcher = EvmWatcher.create(settings)
    watcher.run(SessionFactory)


if __name__ == "__main__":
    main()
