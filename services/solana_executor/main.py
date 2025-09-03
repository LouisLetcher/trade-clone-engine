from loguru import logger

from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import make_session_factory
from trade_clone_engine.execution.solana_executor import SolanaExecutor


def main():
    settings = AppSettings()
    logger.remove()
    logger.add(lambda m: print(m, end=""), level=settings.log_level)

    SessionFactory = make_session_factory(settings.database_url)
    executor = SolanaExecutor.create(settings)
    executor.run(SessionFactory)


if __name__ == "__main__":
    main()

