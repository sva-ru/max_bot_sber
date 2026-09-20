# gigachat_client.py
import logging
import time
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
) -> str:
    """
    Отправляет промпт в GigaChat и возвращает сгенерированный текст.
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
        text = response.messages[0].content[0].text
        return text.strip() if text else ""
    except Exception as e:
        logger.error(f"Ошибка генерации GigaChat: {e}")
        return ""


def generate_text_safe(prompt: str, retries: int = 2) -> str:
    """
    Обёртка над generate_text с повторными попытками.
    Если все попытки провалились — возвращает пустую строку.
    """
    for attempt in range(retries):
        try:
            result = generate_text(prompt)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Попытка {attempt + 1} не удалась: {e}")
            time.sleep(2)
    return ""
