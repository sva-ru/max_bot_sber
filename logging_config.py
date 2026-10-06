# logging_config.py
"""
Настройка логирования проекта.

Все логи идут ТОЛЬКО в stdout (консоль / логи платформы).
Файлового логирования нет — это упрощает работу в контейнерах
и убирает проблемы с правами на запись в /app/logs и /data.
"""
import logging
import sys


def setup_logging(debug: bool = False) -> None:
    """
    Настраивает корневой логгер: вывод только в stdout.

    :param debug: если True — уровень DEBUG, иначе INFO.
    """
    root_level = logging.DEBUG if debug else logging.INFO

    root = logging.getLogger()
    root.setLevel(root_level)

    # Убираем старые обработчики (важно при повторных вызовах)
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(root_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    logging.getLogger(__name__).info(
        "Логирование настроено (только stdout, файловые логи отключены)."
    )