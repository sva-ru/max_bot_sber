# main.py
import asyncio
import logging

from logging_config import setup_logging
from database import init_db
from scheduler import setup_scheduler
from bot import dp, bot as bot_instance


async def main():
    setup_logging(debug=False)
    logger = logging.getLogger(__name__)

    init_db()
    logger.info("База данных инициализирована.")

    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("Планировщик запущен.")

    logger.info("Запуск бота...")
    await dp.start_polling(bot_instance)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Бот остановлен пользователем.")
    except Exception as e:
        logging.getLogger(__name__).error(f"Критическая ошибка: {e}")
