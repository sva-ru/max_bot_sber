# url_utils.py
"""
Утилиты для нормализации ссылок в постах:
- разворачивает редиректы RSS-агрегаторов;
- делает относительные URL абсолютными;
- кодирует кириллицу и спецсимволы;
- убирает UTM-метки;
- проверяет доступность URL.
"""
import logging
from urllib.parse import urlparse, urlunparse, quote, urljoin, parse_qsl, urlencode

import requests

logger = logging.getLogger(__name__)

# Домены-агрегаторы, чьи ссылки требуют разворота
REDIRECT_HOSTS = {
    "feedproxy.google.com",
    "feeds.feedburner.com",
    "rss.app",
    "feed43.com",
}

# Трекинговые параметры
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "yclid", "_openstat", "from", "ref",
}


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
    Полный цикл нормализации URL.
    """
    if not url:
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
    """Проверяет, что URL доступен."""
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
