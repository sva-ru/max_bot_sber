# gigachat_client.py
"""
Асинхронный клиент GigaChat.

Асинхронный клиент (GigaChatAsyncClient) работает через
OpenAI-совместимый endpoint /v1/chat/completions.
Ответ приходит в формате ChatCompletion: response.choices[0].message.content.

Функция _extract_response умеет читать оба формата — и OpenAI-стиль,
и старый GigaChat-нативный (messages[0].content), чтобы быть устойчивой
к изменениям в SDK.
"""
import asyncio
import logging
from typing import Tuple

from gigachat import GigaChatAsyncClient
from gigachat.models import Chat, Messages, MessagesRole

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
            timeout=30,
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


# ================================================================
# Извлечение текста и finish_reason из ответа
# ================================================================

def _content_to_text(content) -> str:
    """Преобразует content (str, list блоков или None) в строку."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif hasattr(item, "text"):
                parts.append(item.text or "")
        return "".join(parts)
    return ""


def _extract_response(response) -> Tuple[str, str]:
    """
    Пытается извлечь текст и finish_reason из ответа GigaChat.
    Поддерживает оба формата:
      - OpenAI-стиль:   response.choices[0].message.content
      - GigaChat-стиль: response.messages[0].content
    """
    text = ""
    finish_reason = "unknown"

    # --- Вариант 1: OpenAI-стиль ---
    choices = getattr(response, "choices", None)
    if choices:
        try:
            choice = choices[0]
            fr = getattr(choice, "finish_reason", None)
            if fr:
                finish_reason = fr
            msg = getattr(choice, "message", None)
            if msg is not None:
                text = _content_to_text(getattr(msg, "content", None))
        except (IndexError, AttributeError, TypeError):
            pass

    # --- Вариант 2: старый GigaChat-нативный стиль ---
    if not text:
        messages = getattr(response, "messages", None)
        if messages:
            try:
                msg = messages[0]
                # Иногда role тоже важен: берём последнее assistant-сообщение
                content = getattr(msg, "content", None)
                text = _content_to_text(content)
            except (IndexError, AttributeError, TypeError):
                pass

    return text.strip() if text else "", finish_reason


# ================================================================
# Основные функции
# ================================================================

async def generate_text(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 1800,
) -> Tuple[str, str]:
    """
    Отправляет промпт в GigaChat асинхронно.
    Возвращает (текст, finish_reason):
      - 'stop'      — нормальное завершение;
      - 'length'    — обрезано по max_tokens;
      - 'blacklist' — сработал тематический фильтр;
      - 'error'     — исключение при запросе.
    """
    client = get_client()
    try:
        chat = Chat(
            messages=[Messages(role=MessagesRole.USER, content=prompt)],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        response = await client.achat(chat)

        text, finish_reason = _extract_response(response)

        # Если текст пустой — логируем структуру ответа для отладки
        if not text:
            attrs = [a for a in dir(response) if not a.startswith("_")][:25]
            logger.warning(
                f"Не удалось извлечь текст из ответа GigaChat. "
                f"Тип: {type(response).__name__}. "
                f"Атрибуты: {attrs}. "
                f"repr: {repr(response)[:400]}"
            )

        return text, finish_reason

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
            await asyncio.sleep(2)

    return "", "error"