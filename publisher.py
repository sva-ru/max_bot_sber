# publisher.py
import logging
from maxapi import Bot
from config import MAX_BOT_TOKEN, CHANNEL_CHAT_ID
from database import save_post, is_url_published
from content_generator import generate_post

logger = logging.getLogger(__name__)

bot = Bot(MAX_BOT_TOKEN)


async def publish_post(force: bool = False) -> bool:
    if not CHANNEL_CHAT_ID:
        logger.error("CHANNEL_CHAT_ID не задан в .env")
        return False

    post = generate_post()

    if post.get("source_url") and not force:
        if is_url_published(post["source_url"]):
            logger.info(f"Пост уже публиковался: {post['source_url']}")
            return False

    try:
        message = await bot.send_message(
            chat_id=CHANNEL_CHAT_ID,
            text=post["content"],
            parse_mode="markdown",
        )
        logger.info(f"Пост опубликован: {post['title']}")
        message_id = getattr(message, "message_id", "")
        save_post(
            title=post["title"],
            content=post["content"],
            source_url=post.get("source_url", ""),
            message_id=str(message_id),
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        return False


async def send_test_message():
    try:
        await bot.send_message(
            chat_id=CHANNEL_CHAT_ID,
            text="✅ Бот успешно подключён к каналу. Публикации настроены.",
        )
        print("Тестовое сообщение отправлено.")
    except Exception as e:
        print(
            f"Ошибка: {e}. Убедитесь, что бот добавлен в администраторы "
            f"канала и CHANNEL_CHAT_ID верен."
        )
