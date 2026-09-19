import logging
from maxapi import Bot, Dispatcher
from maxapi.types import Command, MessageCreated
from config import MAX_BOT_TOKEN
from publisher import publish_post, send_test_message
from database import get_recent_posts

logger = logging.getLogger(__name__)

bot = Bot(MAX_BOT_TOKEN)
dp = Dispatcher()

@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
        await event.message.answer(
                 "👋 Бот для управления каналом «Бизнес-Фактор Юго-Запад».\n\n"
                 "Доступные команды:\n"
                 "/publish — опубликовать пост в канал\n"
                 "/test — отправить тестовое сообщение\n"
                 "/stats — последние опубликованные посты\n"
                 "/help — справка"
        )

@dp.message_created(Command("publish"))
async def cmd_publish(event: MessageCreated):
        await event.message.answer("⏳ Генерирую и публикую пост...")
        success = await publish_post(force=True)
        if success:
            await event.message.answer("✅ Пост опубликован в канал!")
        else:
            await event.message.answer("❌ Не удалось опубликовать пост. Проверьте логи.")

@dp.message_created(Command("test"))
async def cmd_test(event: MessageCreated):
        await send_test_message()
        await event.message.answer("Тестовое сообщение отправлено в канал.")

@dp.message_created(Command("stats"))
async def cmd_stats(event: MessageCreated):
        posts = get_recent_posts(5)
        if not posts:
                await event.message.answer("Публикаций пока не было.")
                return
        text = "📋 **Последние публикации:**\n\n"
        for title, content, published_at in posts:
                text += f"• {title} — {published_at}\n"
        await event.message.answer(text)

@dp.message_created(Command("help"))
async def cmd_help(event: MessageCreated):
        await event.message.answer(
                "Команды:\n"
                "/publish — принудительная публикация\n"
                "/test — проверка подключения к каналу\n"
                "/stats — статистика публикаций\n"
                "/help — это сообщение"
        )
