# gigachat_client.py
import logging
import time
from gigachat import GigaChat
from gigachat.models import ChatCompletionRequest, ChatMessage
from config import GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE

logger = logging.getLogger(__name__)

_client = None


def get_client():
    """Создаёт и кэширует клиент GigaChat."""
    global _client
    if _client is None:
        try:
            _client = GigaChat(
                credentials=GIGACHAT_CREDENTIALS,
                scope=GIGACHAT_SCOPE,
                model="GigaChat-2",  # или "GigaChat-2-Pro" для сложных текстов
                verify_ssl_certs=True
            )
            logger.info("Клиент GigaChat успешно инициализирован.")
        except Exception as e:
            logger.error(f"Ошибка инициализации GigaChat: {e}")
            raise
    return _client

def generate_text(prompt: str, temperature: float = 0.7, max_tokens: int = 800) -> str:
    client = get_client()
    try:
        request = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        response = client.chat.create(request)
        return response.messages[0].content[0].text.strip()
    except Exception as e:
        logger.error(f"Ошибка генерации GigaChat: {e}")
        return ""

def generate_text_safe(prompt: str, retries: int = 2) -> str:
    for attempt in range(retries):
        try:
            return generate_text(prompt)
        except Exception as e:
            logger.warning(f"Попытка {attempt+1} не удалась: {e}")
            time.sleep(2)
    return ""
