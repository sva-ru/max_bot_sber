import asyncio
import logging
from maxapi import Bot, Dispatcher
from config import MAX_BOT_TOKEN
from database import init_db
from scheduler import setup_scheduler
from bot import dp, bot as bot_instance

logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

logging.getLogger("content_generator").setLevel(logging.DEBUG)

async def main():
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
                logger.info("Бот остановлен пользователем.")
        except Exception as e:
                logger.error(f"Критическая ошибка: {e}")