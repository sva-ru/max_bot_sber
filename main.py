# main.py
import asyncio
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from logging_config import setup_logging
from database import init_db
from scheduler import setup_scheduler
from bot import dp, bot as bot_instance
from gigachat_client import close_client


# ================================================================
# HEALTH-СЕРВЕР (отдельный поток, не зависит от event loop)
# ================================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        logger = logging.getLogger("healthcheck")
        logger.info(
            f"PROBE IN: {self.command} {self.path} "
            f"from {self.client_address[0]}"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass

def start_health_server(port: int) -> None:
    """Запускает HTTP health-сервер в daemon-потоке."""
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logging.getLogger(__name__).info(
        f"Health-сервер запущен на порту {port} (отдельный поток)"
    )


# ================================================================
# MAIN
# ================================================================

async def main():
    setup_logging(debug=False)
    logger = logging.getLogger(__name__)

    # Health-сервер поднимаем как можно раньше,
    # чтобы Cloud.ru успел получить первый ответ до readiness probe.
    port = int(os.getenv("PORT", "8080"))
    start_health_server(port)

    init_db()
    logger.info("База данных инициализирована.")

    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("Планировщик запущен.")

    logger.info("Запуск бота...")
    try:
        await dp.start_polling(bot_instance)
    finally:
        # Закрываем клиент GigaChat при остановке
        await close_client()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Бот остановлен пользователем.")
    except Exception as e:
        logging.getLogger(__name__).error(f"Критическая ошибка: {e}")