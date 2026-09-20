import os
from dotenv import load_dotenv

load_dotenv()

MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN")
CHANNEL_CHAT_ID = int(os.getenv("CHANNEL_CHAT_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "4"))

# GigaChat
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_CORP")

# путь к базе
DB_PATH = os.getenv("DB_PATH", "channel_posts.db")