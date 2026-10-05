# database.py
"""
Работа с SQLite: сохранение постов и проверка дублей по URL.
С версии без content/*.json таблица published_content не нужна.
"""
import logging
import sqlite3
from contextlib import contextmanager
from typing import List, Optional, Tuple

from config import DB_PATH

logger = logging.getLogger(__name__)


@contextmanager
def _connect(commit: bool = False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка БД: {e}")
        raise
    finally:
        conn.close()


def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    """Добавляет колонку, если её нет — простая миграция."""
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    if column not in columns:
        logger.info(f"Миграция: добавляю колонку {table}.{column}")
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db():
    with _connect(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source_url TEXT,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_id TEXT,
                ai_generated INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_source_url
            ON posts (source_url)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_published_at
            ON posts (published_at DESC)
        """)

        # Миграции на случай старых схем
        _ensure_column(conn, "posts", "ai_generated", "INTEGER DEFAULT 0")
        _ensure_column(conn, "posts", "message_id", "TEXT")

    logger.info(f"Таблица posts готова ({DB_PATH}).")


def save_post(
    title: str,
    content: str,
    source_url: str = "",
    message_id: str = "",
    ai_generated: bool = False,
) -> Optional[int]:
    with _connect(commit=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO posts (title, content, source_url, message_id, ai_generated)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, content, source_url, message_id, 1 if ai_generated else 0),
        )
        return cur.lastrowid


def is_url_published(source_url: str) -> bool:
    if not source_url:
        return False
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM posts WHERE source_url = ? LIMIT 1",
            (source_url,),
        )
        return cur.fetchone() is not None


def get_recent_posts(limit: int = 10) -> List[Tuple]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT title, content, published_at
            FROM posts
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [(r["title"], r["content"], r["published_at"]) for r in rows]


def get_stats() -> dict:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM posts")
        total = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS ai FROM posts WHERE ai_generated = 1")
        ai_count = cur.fetchone()["ai"]

        cur.execute(
            "SELECT MIN(published_at) AS first, MAX(published_at) AS last FROM posts"
        )
        row = cur.fetchone()

    return {
        "total": total,
        "ai_generated": ai_count,
        "first_post": row["first"],
        "last_post": row["last"],
    }