# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# --- MAX ---
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN")
CHANNEL_CHAT_ID = int(os.getenv("CHANNEL_CHAT_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "4"))

# --- База данных ---
# Локально — файл в проекте; на Railway — /data/channel_posts.db
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "channel_posts.db"))

# --- GigaChat ---
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2")