# gigachat_client.py
"""
Клиент GigaChat.

Возвращает не только текст, но и finish_reason, чтобы вызывающий код
мог отличить нормальный ответ от отказа модели (blacklist).
"""
import logging
import time
from typing import Tuple

from gigachat import GigaChat
from gigachat.models import ChatCompletionRequest, ChatMessage

from config import GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE, GIGACHAT_MODEL

logger = logging.getLogger(__name__)

_client = None


def get_client() -> GigaChat:
    """Ленивая инициализация клиента GigaChat."""
    global _client
    if _client is None:
        if not GIGACHAT_CREDENTIALS:
            raise ValueError("GIGACHAT_CREDENTIALS не задан в .env")
        _client = GigaChat(
            credentials=GIGACHAT_CREDENTIALS,
            scope=GIGACHAT_SCOPE,
            model=GIGACHAT_MODEL,
            verify_ssl_certs=True,
        )
        logger.info("Клиент GigaChat успешно инициализирован.")
    return _client


def generate_text(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 1800,
) -> Tuple[str, str]:
    """
    Отправляет промпт в GigaChat.

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
        response = client.chat.create(request)

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
        logger.error(f"Ошибка генерации GigaChat: {e}")
        return "", "error"


def generate_text_safe(prompt: str, retries: int = 2) -> Tuple[str, str]:
    """
    Обёртка над generate_text с повторными попытками.

    При blacklist повторять бессмысленно — сразу возвращаем наверх.
    При прочих ошибках пробуем retries раз с паузой.
    """
    for attempt in range(retries):
        try:
            text, reason = generate_text(prompt)

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
            time.sleep(2)

    return "", "error"