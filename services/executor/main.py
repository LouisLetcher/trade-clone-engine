from loguru import logger

from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import make_session_factory
from trade_clone_engine.execution.evm_executor import EvmExecutor


def main():
    settings = AppSettings()
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=settings.log_level)

    SessionFactory = make_session_factory(settings.database_url)

    exec = EvmExecutor(settings)
    exec.run(SessionFactory)


if __name__ == "__main__":
    main()

