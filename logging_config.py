# logging_config.py
"""
Настройка логирования проекта.

Основной лог       → stdout + logs/channel.log (INFO+)
Лог отбраковки RSS → logs/rss_rejected.log (DEBUG, только отброшенные)
"""
import logging
import sys
from pathlib import Path

# logging_config.py
BASE_DIR = Path(__file__).parent
# Логи пишем в /data, где смонтирован постоянный том с правами UID 1000
LOG_DIR = Path("/data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

MAIN_LOG = LOG_DIR / "channel.log"
REJECTED_LOG = LOG_DIR / "rss_rejected.log"


def setup_logging(debug: bool = False) -> None:
    root_level = logging.DEBUG if debug else logging.INFO

    # --- Основной логгер ---
    root = logging.getLogger()
    root.setLevel(root_level)

    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(root_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    main_file = logging.FileHandler(MAIN_LOG, mode="a", encoding="utf-8")
    main_file.setLevel(root_level)
    main_file.setFormatter(formatter)
    root.addHandler(main_file)

    # --- Отдельный логгер отбраковки RSS ---
    rejected = logging.getLogger("rss_rejected")
    rejected.setLevel(logging.DEBUG)
    rejected.propagate = False

    for h in list(rejected.handlers):
        rejected.removeHandler(h)

    rejected_file = logging.FileHandler(REJECTED_LOG, mode="w", encoding="utf-8")
    rejected_file.setLevel(logging.DEBUG)
    rejected_file.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    rejected.addHandler(rejected_file)

    logging.getLogger(__name__).info(
        f"Логирование настроено. Основной лог: {MAIN_LOG.name}, "
        f"отбраковка RSS: {REJECTED_LOG.name}"
    )