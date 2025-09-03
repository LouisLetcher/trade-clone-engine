from loguru import logger

from trade_clone_engine.config import AppSettings
from trade_clone_engine.discovery.runner import main_loop, run_discovery_once


def main():
    logger.remove()
    logger.add(lambda m: print(m, end=""))
    settings = AppSettings()
    if settings.discover_once:
        run_discovery_once(settings)
    else:
        main_loop()


if __name__ == "__main__":
    main()
