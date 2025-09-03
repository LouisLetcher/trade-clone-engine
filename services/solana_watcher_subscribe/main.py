import asyncio
from loguru import logger

from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import make_session_factory
from trade_clone_engine.chains.solana_watcher import SolanaWatcher


def main():
    settings = AppSettings()
    logger.remove()
    logger.add(lambda m: print(m, end=""), level=settings.log_level)

    SessionFactory = make_session_factory(settings.database_url)
    watcher = SolanaWatcher.create(settings)
    logger.info("Solana watcher subscribe container: forcing subscription mode")
    asyncio.run(watcher.run_subscribe(SessionFactory))


if __name__ == "__main__":
    main()

