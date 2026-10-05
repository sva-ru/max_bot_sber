# url_utils.py
"""
Утилиты для нормализации ссылок в постах:
- разворачивает редиректы RSS-агрегаторов;
- делает относительные URL абсолютными;
- кодирует кириллицу и спецсимволы;
- убирает UTM-метки;
- проверяет доступность URL (с кэшированием).
"""
import logging
import time
from urllib.parse import urlparse, urlunparse, quote, urljoin, parse_qsl, urlencode

import requests

logger = logging.getLogger(__name__)

# Домены-агрегаторы, чьи ссылки требуют разворота
REDIRECT_HOSTS = {
    "feedproxy.google.com",
    "feeds.feedburner.com",
    "rss.app",
    "feed43.com",
    "rsshub.app",
    "feedly.com",
    "inoreader.com",
    "news.google.com",
    "zen.yandex.ru",
}

# Трекинговые параметры
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "yclid", "_openstat", "from", "ref",
}

# Домены-заглушки
FAKE_DOMAINS = {
    "пример-пресс-релиза.ru",
    "example.com",
    "test.ru",
}

# Кэш проверки ссылок: {url: (is_alive, timestamp)}
_VALIDATE_CACHE = {}
_CACHE_TTL = 3600  # 1 час


def _strip_tracking(url: str) -> str:
    """Убирает UTM-метки и прочие трекинговые параметры."""
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url
        clean = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        return urlunparse(parsed._replace(query=urlencode(clean)))
    except Exception:
        return url


def _encode_cyrillic(url: str) -> str:
    """Кодирует кириллицу и пробелы в URL."""
    try:
        parsed = urlparse(url)
        return urlunparse(parsed._replace(
            path=quote(parsed.path, safe="/"),
            query=quote(parsed.query, safe="=&?"),
        ))
    except Exception:
        return url


def _make_absolute(url: str, source_url: str) -> str:
    """Превращает относительный URL в абсолютный."""
    if url.startswith(("http://", "https://")):
        return url
    return urljoin(source_url, url)


def resolve_url(url: str, source_url: str = "", timeout: int = 8) -> str:
    """
    Полный цикл нормализации URL:
    1. Абсолютный ли путь.
    2. Разворот редиректов (для известных агрегаторов).
    3. Очистка трекинговых параметров.
    4. Кодирование кириллицы.
    """
    if not url:
        return ""

    # Отсекаем заглушки
    parsed = urlparse(url)
    if parsed.netloc.lower() in FAKE_DOMAINS:
        logger.warning(f"Отброшена ссылка-заглушка: {url}")
        return ""

    url = _make_absolute(url, source_url)
    url = _strip_tracking(url)

    host = urlparse(url).netloc.lower()
    if host in REDIRECT_HOSTS:
        try:
            resp = requests.head(
                url, allow_redirects=True, timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            final = resp.url
            if final and final != url:
                logger.debug(f"Редирект {url} → {final}")
                url = final
        except Exception as e:
            logger.warning(f"Не удалось развернуть редирект {url}: {e}")

    return _encode_cyrillic(url)


def is_url_alive(url: str, timeout: int = 5) -> bool:
    """Проверяет доступность URL без кэширования."""
    if not url:
        return False
    try:
        resp = requests.get(
            url, allow_redirects=True, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
            stream=True,
        )
        return resp.status_code < 400
    except Exception as e:
        logger.warning(f"URL недоступен {url}: {e}")
        return False


def validate_source_url(url: str, timeout: int = 5) -> bool:
    """
    Проверяет, что URL-источник реально открывается (HTTP 200).
    Отсекает заглушки и битые ссылки.
    Результат кэшируется на _CACHE_TTL секунд.
    """
    if not url:
        return False

    parsed = urlparse(url)
    if parsed.netloc.lower() in FAKE_DOMAINS:
        logger.warning(f"Заглушка вместо ссылки: {url}")
        return False

    # Проверка кэша
    now = time.time()
    cached = _VALIDATE_CACHE.get(url)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    try:
        resp = requests.head(
            url, allow_redirects=True, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        # Некоторые сайты не поддерживают HEAD — повторяем GET
        if resp.status_code == 405:
            resp = requests.get(
                url, allow_redirects=True, timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0"},
                stream=True,
            )

        ok = resp.status_code < 400
        if not ok:
            logger.warning(f"Источник недоступен [{resp.status_code}]: {url}")

        _VALIDATE_CACHE[url] = (ok, now)
        return ok
    except Exception as e:
        logger.warning(f"Ошибка проверки ссылки {url}: {e}")
        _VALIDATE_CACHE[url] = (False, now)
        return False