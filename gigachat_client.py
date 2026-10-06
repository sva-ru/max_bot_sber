# gigachat_client.py
"""
Асинхронный клиент GigaChat.

Возвращает (текст, finish_reason), чтобы вызывающий код
мог отличить нормальный ответ от отказа модели (blacklist).

Все запросы — нативные async через GigaChatAsyncClient,
с явным таймаутом, чтобы не блокировать event loop.
"""
import asyncio
import logging
from typing import Tuple

from gigachat import GigaChatAsyncClient
from gigachat.models import ChatCompletionRequest, ChatMessage

from config import GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE, GIGACHAT_MODEL

logger = logging.getLogger(__name__)

_client: GigaChatAsyncClient | None = None


def get_client() -> GigaChatAsyncClient:
    """Ленивая инициализация асинхронного клиента GigaChat."""
    global _client
    if _client is None:
        if not GIGACHAT_CREDENTIALS:
            raise ValueError("GIGACHAT_CREDENTIALS не задан в .env")
        _client = GigaChatAsyncClient(
            credentials=GIGACHAT_CREDENTIALS,
            scope=GIGACHAT_SCOPE,
            model=GIGACHAT_MODEL,
            verify_ssl_certs=True,
            timeout=30,  # общий таймаут на HTTP-запросы (сек)
        )
        logger.info("Клиент GigaChat (async) успешно инициализирован.")
    return _client


async def close_client() -> None:
    """Закрывает HTTP-соединения при остановке бота."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
            logger.info("Клиент GigaChat закрыт.")
        except Exception as e:
            logger.warning(f"Ошибка при закрытии клиента GigaChat: {e}")
        finally:
            _client = None


async def generate_text(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 1800,
) -> Tuple[str, str]:
    """
    Отправляет промпт в GigaChat асинхронно.

    Возвращает кортеж (текст, finish_reason):
      - 'stop'      — нормальное завершение;
      - 'length'    — обрезано по max_tokens;
      - 'blacklist' — сработал тематический фильтр (отказ модели);
      - 'error'     — исключение при запросе.
    """
    client = get_client()
    try:
        request = ChatCompletionRequest(
            model=GIGACHAT_MODEL,
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        response = await client.achat(request)

        text = ""
        if getattr(response, "messages", None):
            try:
                text = response.messages[0].content[0].text or ""
            except (IndexError, AttributeError, TypeError):
                text = ""

        finish_reason = "unknown"
        if getattr(response, "choices", None):
            try:
                finish_reason = response.choices[0].finish_reason or "unknown"
            except (IndexError, AttributeError, TypeError):
                finish_reason = "unknown"

        return text.strip(), finish_reason
    except Exception as e:
        logger.error(f"Ошибка генерации GigaChat: {type(e).__name__}: {e}")
        return "", "error"


async def generate_text_safe(prompt: str, retries: int = 2) -> Tuple[str, str]:
    """
    Обёртка с повторными попытками.
    При blacklist повторять бессмысленно — сразу возвращаем наверх.
    """
    for attempt in range(retries):
        try:
            text, reason = await generate_text(prompt)

            if reason == "blacklist":
                logger.warning(
                    "GigaChat: тематическое ограничение (blacklist), "
                    "повторные попытки не выполняются"
                )
                return "", "blacklist"

            if text:
                return text, reason

        except Exception as e:
            logger.warning(f"Попытка {attempt + 1} не удалась: {e}")

        if attempt < retries - 1:
            await asyncio.sleep(2)  # асинхронная пауза, не блокирует loop

    return "", "error"