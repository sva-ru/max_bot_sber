# main.py
import asyncio
import logging
import os

from aiohttp import web

from logging_config import setup_logging
from database import init_db
from scheduler import setup_scheduler
from bot import dp, bot as bot_instance


# ---------- Health-сервер для Cloud.ru ----------
async def _health(request):
    return web.Response(text="OK", status=200)


async def start_health_server():
    """
    Поднимает HTTP-сервер на порту из $PORT (или 8080).
    Отвечает 200 OK на любой GET — этого достаточно для liveness probe.
    """
    port = int(os.getenv("PORT", "8080"))
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    app.router.add_get("/healthz", _health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.getLogger(__name__).info(f"Health-сервер запущен на порту {port}")


# ---------- main ----------
async def main():
    setup_logging(debug=False)
    logger = logging.getLogger(__name__)

    init_db()
    logger.info("База данных инициализирована.")

    # Запускаем health-сервер параллельно с ботом
    await start_health_server()

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