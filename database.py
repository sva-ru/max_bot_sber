
# database.py
import sqlite3
from config import DB_PATH


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            source_url TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message_id TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_post(title: str, content: str, source_url: str = "", message_id: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO posts (title, content, source_url, message_id) "
        "VALUES (?, ?, ?, ?)",
        (title, content, source_url, message_id)
    )
    conn.commit()
    conn.close()


def is_url_published(source_url: str) -> bool:
    if not source_url:
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM posts WHERE source_url = ? LIMIT 1", (source_url,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_recent_posts(limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, content, published_at FROM posts "
        "ORDER BY published_at DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows