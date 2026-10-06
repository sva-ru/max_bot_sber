# gigachat_client.py
"""
Асинхронный клиент GigaChat с защитой от 429 Too Many Requests.

Исправления:
- Добавлен семафор (asyncio.Semaphore(1)) для строго последовательных запросов.
- Настроены автоматические повторные попытки (max_retries, retry_backoff_factor).
- Добавлена пауза между запросами (RATE_LIMIT_DELAY).
- Обработка RateLimitError с учётом retry_after.
"""
import asyncio
import logging
from typing import Tuple

from gigachat import GigaChatAsyncClient
from gigachat.models import Chat, Messages, MessagesRole
from gigachat.exceptions import RateLimitError

from config import GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE, GIGACHAT_MODEL

logger = logging.getLogger(__name__)

# ================================================================
# НАСТРОЙКИ
# ================================================================

# Семафор на 1: одновременно выполняется только один запрос к GigaChat.
# Это критически важно для физических лиц (лимит: 1 поток).
_request_semaphore = asyncio.Semaphore(1)

# Пауза между последовательными запросами (в секундах).
# Помогает не упираться в лимит запросов в минуту.
RATE_LIMIT_DELAY = 1.0

# Количество повторных попыток при 429 (обрабатывается библиотекой).
MAX_RETRIES = 3

# Множитель экспоненциальной задержки: 0.5s, 1s, 2s и т.д.
RETRY_BACKOFF_FACTOR = 0.5

_client: GigaChatAsyncClient | None = None


# ================================================================
# КЛИЕНТ
# ================================================================

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
            max_retries=MAX_RETRIES,
            retry_backoff_factor=RETRY_BACKOFF_FACTOR,
            retry_on_status_codes=(429, 500, 502, 503, 504),
        )
        logger.info(
            f"Клиент GigaChat (async) инициализирован. "
            f"max_retries={MAX_RETRIES}, backoff={RETRY_BACKOFF_FACTOR}"
        )
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
# ИЗВЛЕЧЕНИЕ ОТВЕТА
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
    """Извлекает текст и finish_reason из ответа GigaChat."""
    text = ""
    finish_reason = "unknown"

    # OpenAI-стиль: response.choices[0].message.content
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

    # Старый GigaChat-стиль: response.messages[0].content
    if not text:
        messages = getattr(response, "messages", None)
        if messages:
            try:
                msg = messages[0]
                text = _content_to_text(getattr(msg, "content", None))
            except (IndexError, AttributeError, TypeError):
                pass

    return text.strip() if text else "", finish_reason


# ================================================================
# ГЕНЕРАЦИЯ ТЕКСТА
# ================================================================

async def generate_text(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 1800,
) -> Tuple[str, str]:
    """
    Отправляет промпт в GigaChat с защитой от 429.

    Использует семафор для последовательных запросов.
    При ошибке 429 библиотека автоматически повторит попытку
    с экспоненциальной задержкой.
    """
    client = get_client()

    # === Семафор: пропускаем только один запрос одновременно ===
    async with _request_semaphore:
        try:
            chat = Chat(
                messages=[Messages(role=MessagesRole.USER, content=prompt)],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            response = await client.achat(chat)

            # Небольшая пауза после успешного запроса,
            # чтобы не упираться в лимит запросов в минуту.
            await asyncio.sleep(RATE_LIMIT_DELAY)

            text, finish_reason = _extract_response(response)

            if not text:
                attrs = [a for a in dir(response) if not a.startswith("_")][:25]
                logger.warning(
                    f"Не удалось извлечь текст из ответа GigaChat. "
                    f"Тип: {type(response).__name__}. "
                    f"Атрибуты: {attrs}. repr: {repr(response)[:400]}"
                )

            return text, finish_reason

        except RateLimitError as e:
            # Библиотека уже сделала max_retries попыток.
            # Если 429 всё ещё приходит — ждём рекомендованное время.
            retry_after = getattr(e, "retry_after", 5) or 5
            logger.error(
                f"GigaChat: 429 Too Many Requests. "
                f"Лимит запросов исчерпан. Жду {retry_after} сек."
            )
            await asyncio.sleep(retry_after)
            return "", "error"

        except Exception as e:
            logger.error(f"Ошибка генерации GigaChat: {type(e).__name__}: {e}")
            return "", "error"


async def generate_text_safe(prompt: str, retries: int = 2) -> Tuple[str, str]:
    """
    Обёртка с повторными попытками.
    При blacklist повторять бессмысленно — сразу возвращаем наверх.
    При 429 библиотека уже сделала свои повторы.
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
            # Дополнительная пауза перед повторной попыткой
            await asyncio.sleep(3)

    return "", "error"