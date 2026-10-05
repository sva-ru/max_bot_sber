# config.py
"""
Конфигурация проекта канала «Бизнес-Фактор Юго-Запад».
Хранилище — SQLite. Все значения читаются из .env.
Здесь не должно быть импортов из других модулей проекта —
только стандартная библиотека и dotenv.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# ================================================================
# ПУТИ
# ================================================================

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"


# ================================================================
# MAX (мессенджер)
# ================================================================

MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
CHANNEL_CHAT_ID = int(os.getenv("CHANNEL_CHAT_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "2"))


# ================================================================
# ФИЛЬТР ДАТ ДЛЯ RSS
# ================================================================

DATE_FILTER = os.getenv("DATE_FILTER", "year").strip().lower()
if DATE_FILTER not in ("quarter", "year", "none"):
    print(
        f"[config] Некорректное значение DATE_FILTER={DATE_FILTER!r}. "
        f"Использую 'year'."
    )
    DATE_FILTER = "year"


# ================================================================
# SQLITE
# ================================================================

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "channel_posts.db"))


# ================================================================
# GIGACHAT
# ================================================================

GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2")


# ================================================================
# RSSHUB
# ================================================================

RSSHUB_ACCESS_KEY = os.getenv("RSSHUB_ACCESS_KEY", "")
RSSHUB_BASE_URL = os.getenv("RSSHUB_BASE_URL", "").rstrip("/")


# ================================================================
# ВАЛИДАЦИЯ
# ================================================================

def _validate():
    missing = []
    if not MAX_BOT_TOKEN:
        missing.append("MAX_BOT_TOKEN")
    if not CHANNEL_CHAT_ID:
        missing.append("CHANNEL_CHAT_ID")
    if not GIGACHAT_CREDENTIALS:
        missing.append("GIGACHAT_CREDENTIALS")

    if missing:
        print(
            f"[config] ВНИМАНИЕ: не заданы переменные окружения: "
            f"{', '.join(missing)}. Проверьте файл .env"
        )

    if RSSHUB_BASE_URL and not RSSHUB_ACCESS_KEY:
        print(
            "[config] ВНИМАНИЕ: RSSHUB_BASE_URL задан, "
            "но RSSHUB_ACCESS_KEY пуст — ленты RSSHub не будут работать."
        )


_validate()