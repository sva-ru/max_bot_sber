# content_generator.py (начало файла)
import json
import logging
import random
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, List

import feedparser

from gigachat_client import generate_text_safe
from config import CONTENT_DIR
from url_utils import resolve_url, validate_source_url


logger = logging.getLogger(__name__)
rejected = logging.getLogger("rss_rejected")

RSS_SOURCES = [
    "https://sberbank.ru/ru/s_m_business/news/rss",
    "https://kuban.rbc.ru/rss",
    "https://rostov.rbc.ru/rss",
    "https://expertsouth.ru/rss/",
    "https://stav.aif.ru/rss",
]


# ================================================================
# ФИЛЬТР ПО ДАТЕ
# ================================================================

def current_quarter(d: Optional[date] = None) -> int:
    d = d or date.today()
    return (d.month - 1) // 3 + 1


def parse_entry_date(entry) -> Optional[date]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday)
            except Exception:
                continue
    return None


def is_current_period(entry_date: Optional[date]) -> bool:
    if entry_date is None:
        return False
    today = date.today()
    if entry_date.year != today.year:
        return False
    if current_quarter(entry_date) != current_quarter(today):
        return False
    return True


# ================================================================
# ИЗВЛЕЧЕНИЕ ИНН И НАЗВАНИЙ КОМПАНИЙ
# ================================================================

INN_PATTERN = re.compile(r"\b(?:ИНН[:\s]*)?(\d{10}|\d{12})\b")
ORG_NAME_PATTERN = re.compile(
    r"\b(ООО|АО|ПАО|ЗАО|ОАО|ИП)\s+[«\"]([^»\"]{2,60})[»\"]"
)
ORG_NAME_PATTERN_2 = re.compile(
    r"\b(ООО|АО|ПАО|ЗАО|ОАО)\s+([А-ЯЁ][А-Яа-яЁё0-9\-]{2,40})"
)
URL_PATTERN = re.compile(r"https?://[^\s\)\]\}\>]+")


def extract_inn(text: str) -> Optional[str]:
    if not text:
        return None
    m = INN_PATTERN.search(text)
    return m.group(1) if m else None


def extract_company_name(text: str) -> Optional[str]:
    if not text:
        return None
    m = ORG_NAME_PATTERN.search(text)
    if m:
        return f"{m.group(1)} «{m.group(2)}»"
    m = ORG_NAME_PATTERN_2.search(text)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return None


def extract_urls(text: str) -> list:
    return URL_PATTERN.findall(text or "")

# ================================================================
# ЗАГРУЗКА КЕЙСОВ И АНАЛИТИКИ ИЗ JSON
# ================================================================

CASES_FILE = Path(CONTENT_DIR) / "cases.json"
ANALYTICS_FILE = Path(CONTENT_DIR) / "analytics.json"


def load_cases() -> List[Dict]:
    """
    Читает кейсы из content/cases.json.
    Файл перечитывается при каждом вызове — правки видны без перезапуска.
    """
    if not CASES_FILE.exists():
        logger.warning(f"Файл кейсов не найден: {CASES_FILE}")
        return []
    try:
        with CASES_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error(f"cases.json должен содержать массив, а не {type(data)}")
            return []
        logger.debug(f"Загружено кейсов: {len(data)}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка JSON в cases.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Ошибка чтения cases.json: {e}")
        return []


def load_analytics() -> List[Dict]:
    """
    Читает аналитику из content/analytics.json.
    Файл перечитывается при каждом вызове.
    """
    if not ANALYTICS_FILE.exists():
        logger.warning(f"Файл аналитики не найден: {ANALYTICS_FILE}")
        return []
    try:
        with ANALYTICS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error(f"analytics.json должен содержать массив, а не {type(data)}")
            return []
        logger.debug(f"Загружено аналитики: {len(data)}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка JSON в analytics.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Ошибка чтения analytics.json: {e}")
        return []

# ================================================================
# ШАБЛОНЫ
# ================================================================

TEMPLATES = {
    "news": (
        "📊 **{title}**\n\n"
        "{client_block}"
        "{summary}\n\n"
        "💡 **Что это значит для бизнеса Юга России:**\n"
        "{insight}\n\n"
        "🔗 Первоисточник:\n{link}\n\n"
        "#ЮгБизнес #СберЮЗБ #КрупныйБизнес #{industry_tag}"
    ),

    "case": (
        "💼 **Кейс клиента Юго-Западного банка**\n\n"
        "{client_block}"
        "📌 **Отрасль:** {industry}\n"
        "📍 **Регион:** {region}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🤝 **Сделка:** {deal_type}\n"
        "💰 **Сумма:** {deal_amount}\n"
        "⏳ **Срок:** {deal_term}\n"
        "🏛️ **Место проведения сделки:** {deal_place}\n"
        "📅 **Период:** {deal_period}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 **Цель финансирования:**\n"
        "{purpose}\n\n"
        "⚙️ **Структура сделки:**\n"
        "{structure}\n\n"
        "📈 **Результат для клиента:**\n"
        "{result}\n\n"
        "🌍 **Эффект для региона:**\n"
        "{region_effect}\n\n"
        "🔗 Первоисточник:\n{source_url}\n\n"
        "#КейсыКлиентов #СберЮЗБ #БизнесЮга #{industry_tag}"
    ),

    "analytics": (
    "📈 **Аналитика для крупного и среднего бизнеса**\n\n"
    "{content}\n\n"
    "💼 **Практический вывод:**\n"
    "{insight}\n\n"
    "🔗 Источник: {source}\n"
    "{source_url_line}\n"
    "#Аналитика #БизнесЮга #СберЮЗБ #{industry_tag}"
    ),
}

# ================================================================
# RSS СБОР С ФИЛЬТРАЦИЕЙ И ЛОГИРОВАНИЕМ
# ================================================================

def fetch_rss_news(limit_per_source: int = 10) -> List[Dict]:
    """
    Собирает RSS-новости за текущий год и квартал.
    Принятые → основной лог + возвращаемый список.
    Отброшенные → rss_rejected.log (DEBUG).
    """
    news_items: List[Dict] = []
    today = date.today()
    q = current_quarter(today)

    stats = {
        "total": 0, "accepted": 0,
        "wrong_year": 0, "wrong_quarter": 0, "no_date": 0,
        "with_inn": 0, "with_company": 0,
    }

    logger.info(
        f"Начинаю сбор RSS. Период: {today.year} год, {q} квартал. "
        f"Источников: {len(RSS_SOURCES)}"
    )

    rejected.info("=" * 90)
    rejected.info(
        f"ОТБРАКОВКА RSS. Запуск: {datetime.now():%Y-%m-%d %H:%M:%S}. "
        f"Период: {today.year} год, {q} квартал"
    )
    rejected.info("=" * 90)

    for url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            src_total = len(feed.entries)
            src_accepted = 0
            src_wrong_year = 0
            src_wrong_quarter = 0
            src_no_date = 0

            if src_total == 0:
                logger.warning(f"[{url}] лента пуста (0 записей)")
                rejected.info(f"[{url}] ЛЕНТА ПУСТА")
                continue

            rejected.info(f"\n--- Источник: {url} (всего {src_total}) ---")

            for entry in feed.entries:
                stats["total"] += 1
                entry_date = parse_entry_date(entry)
                title = entry.get("title", "—")[:80]
                raw_link = entry.get("link", "")

                # Фильтр: нет даты
                if entry_date is None:
                    stats["no_date"] += 1
                    src_no_date += 1
                    rejected.info(
                        f"  [NO_DATE] «{title}»\n"
                        f"            ссылка: {raw_link}"
                    )
                    continue

                # Фильтр: не текущий год
                if entry_date.year != today.year:
                    stats["wrong_year"] += 1
                    src_wrong_year += 1
                    rejected.info(
                        f"  [WRONG_YEAR {entry_date.year}] «{title}»\n"
                        f"            ссылка: {raw_link}"
                    )
                    continue

                # Фильтр: не текущий квартал
                if current_quarter(entry_date) != q:
                    stats["wrong_quarter"] += 1
                    src_wrong_quarter += 1
                    rejected.info(
                        f"  [WRONG_QUARTER Q{current_quarter(entry_date)}] "
                        f"«{title}»\n"
                        f"            дата: {entry_date.isoformat()}\n"
                        f"            ссылка: {raw_link}"
                    )
                    continue

                # Принято
                stats["accepted"] += 1
                src_accepted += 1

                summary = entry.get("summary", "")
                full_text = f"{title} {summary}"

                inn = extract_inn(full_text)
                company = extract_company_name(full_text)

                if inn:
                    stats["with_inn"] += 1
                if company:
                    stats["with_company"] += 1

                # Нормализация ссылки
                clean_link = resolve_url(raw_link, source_url=url)

                news_items.append({
                    "title": title,
                    "summary": summary[:700],
                    "link": clean_link,
                    "raw_link": raw_link,
                    "published_date": entry_date.isoformat(),
                    "source": url,
                    "inn": inn,
                    "company": company,
                })

                logger.debug(
                    f"[{url}] ПРИНЯТО ({entry_date.isoformat()}): «{title}»"
                    + (f" | ИНН: {inn}" if inn else "")
                    + (f" | Компания: {company}" if company else "")
                )

                if src_accepted >= limit_per_source:
                    rejected.info(
                        f"  (достигнут лимит {limit_per_source})"
                    )
                    break

            logger.info(
                f"[{url}] всего {src_total} | принято {src_accepted} | "
                f"отброшено: год {src_wrong_year}, "
                f"квартал {src_wrong_quarter}, без даты {src_no_date}"
            )

        except Exception as e:
            logger.warning(f"Ошибка загрузки RSS {url}: {e}")
            rejected.info(f"[{url}] ОШИБКА ЗАГРУЗКИ: {e}")

    rejected_count = stats["total"] - stats["accepted"]
    summary_text = (
        f"=== ИТОГ СБОРА RSS ===\n"
        f"  Всего записей: {stats['total']}\n"
        f"  Принято: {stats['accepted']} "
        f"(с ИНН: {stats['with_inn']}, "
        f"с компанией: {stats['with_company']})\n"
        f"  Отброшено: {rejected_count} "
        f"(год: {stats['wrong_year']}, "
        f"квартал: {stats['wrong_quarter']}, "
        f"без даты: {stats['no_date']})\n"
        f"  Период: {today.year} год, {q} квартал"
    )
    logger.info(summary_text)

    rejected.info("\n" + "=" * 90)
    rejected.info(summary_text)
    rejected.info("=" * 90)

    if stats["accepted"] == 0:
        logger.warning(
            f"ВНИМАНИЕ: за {today.year} год, {q} квартал не найдено "
            f"ни одной новости. Проверьте RSS-источники."
        )

    return news_items


# ================================================================
# ХЭШТЕГ ОТРАСЛИ
# ================================================================

def _industry_tag(industry: str) -> str:
    return (
        industry.replace(" ", "").replace("-", "").replace("/", "")
        or "Бизнес"
    )


# ================================================================
# ГАРАНТИЯ ССЫЛКИ В ПОСТЕ
# ================================================================

def _ensure_source_link(text: str, source_url: str) -> str:
    """Гарантирует, что в тексте есть ссылка на первоисточник."""
    if not source_url:
        return text

    urls_in_text = extract_urls(text)
    tail = source_url.replace("https://", "").replace("http://", "").rstrip("/")

    for u in urls_in_text:
        if tail and tail in u:
            return text

    return text.rstrip() + f"\n\n🔗 Первоисточник:\n{source_url}"


# ================================================================
# НОВОСТЬ → ПОСТ
# ================================================================

def generate_news_post_with_ai(news_item: Dict) -> Optional[Dict]:
    if not news_item.get("title"):
        return None

    today = date.today()
    quarter = current_quarter(today)
    period_line = f"{today.year} год, {quarter} квартал"

    known_facts = []
    if news_item.get("company"):
        known_facts.append(f"Компания (из источника): {news_item['company']}")
    if news_item.get("inn"):
        known_facts.append(f"ИНН (из источника): {news_item['inn']}")

    facts_block = "\n".join(known_facts) if known_facts else "—"

    prompt = f"""Ты — редактор делового канала «Бизнес-Фактор Юго-Запад» для клиентов крупного и среднего бизнеса Юго-Западного банка Сбербанка России.

Напиши развёрнутый пост на основе новости.

Исходные данные:
Заголовок: {news_item['title']}
Содержание: {news_item.get('summary', '')}
Ссылка (используй как есть, не изменяй): {news_item.get('link', '')}
Дата публикации: {news_item.get('published_date', '—')}
Период: {period_line}

Известные факты о сделке/компании (только они достоверны):
{facts_block}

Жёсткие правила:
1. Период публикации — только текущий год и текущий квартал.
2. ИНН и название компании упоминай ТОЛЬКО если они есть в блоке «Известные факты». Если блока нет — не выдумывай.
3. Никаких данных «по слухам» — только то, что есть в исходных данных.
4. Объём: 1000–1800 символов.
5. Структура:
   • Яркий заголовок с эмодзи (📊, 💼, 📈, 🏭).
   • Абзац 1 — суть: что произошло, кто участники, где, когда.
   • Абзац 2 — детали: суммы, условия, сроки, отрасли, регионы.
   • Абзац 3 — «Что это значит для бизнеса Юга России»: практический вывод для предпринимателей Краснодарского края, Ростовской области, Ставрополья, Крыма и Северного Кавказа.
   • 4–5 релевантных хэштегов в конце.
6. Не упоминай, что текст сгенерирован ИИ.

Выведи только готовый текст поста, без пояснений.
"""
    generated = generate_text_safe(prompt, retries=2)

    if not generated:
        return generate_news_post(news_item)

    link = news_item.get("link", "")
    generated = _ensure_source_link(generated, link)

    return {
        "title": news_item["title"],
        "content": generated,
        "source_url": link,
        "ai_generated": True,
    }


def generate_news_post(news_item: Dict) -> Optional[Dict]:
    """Фолбэк без GigaChat."""
    if not news_item.get("title"):
        return None

    client_block = ""
    if news_item.get("company"):
        client_block += f"🏢 **Клиент:** {news_item['company']}\n"
    if news_item.get("inn"):
        client_block += f"🆔 **ИНН:** {news_item['inn']}\n"
    if client_block:
        client_block += "\n"

    content = TEMPLATES["news"].format(
        title=news_item["title"],
        client_block=client_block,
        summary=news_item.get("summary", "Подробности по ссылке."),
        insight=(
            "Событие актуально для текущего квартала и может повлиять "
            "на условия работы компаний в регионе."
        ),
        link=news_item.get("link", ""),
        industry_tag="Бизнес",
    )
    return {
        "title": news_item["title"],
        "content": content,
        "source_url": news_item.get("link", ""),
    }


# ================================================================
# КЕЙС → ПОСТ
# ================================================================

def generate_case_post() -> Optional[Dict]:
    """
    Формирует пост-кейс из content/cases.json.
    - Отбирает кейсы за текущий год.
    - Проверяет, что source_url реально открывается.
    - Блок «Клиент/ИНН» выводится только при рабочей ссылке.
    """
    cases = load_cases()
    if not cases:
        logger.warning("Список кейсов пуст или файл не найден")
        return None

    today = date.today()
    relevant = [c for c in cases if c.get("year") == today.year]
    dropped = len(cases) - len(relevant)

    if dropped > 0:
        logger.info(
            f"Кейсы: всего {len(cases)}, за {today.year} год — "
            f"{len(relevant)}, отброшено по году — {dropped}"
        )

    if not relevant:
        logger.warning(f"Нет кейсов за {today.year} год — рубрика пропущена")
        return None

    case = random.choice(relevant)

    # --- Проверка ссылки на первоисточник ---
    src_url = case.get("source_url", "").strip()
    source_ok = validate_source_url(src_url)
    if not source_ok:
        if src_url:
            logger.warning(
                f"Ссылка-источник не работает, скрываю: {src_url}"
            )
        src_url = ""

    # --- Блок «клиент» — только если есть рабочая публичная ссылка ---
    client_block = ""
    if source_ok:
        if case.get("client_name"):
            client_block += f"🏢 **Клиент:** {case['client_name']}\n"
        if case.get("client_inn"):
            client_block += f"🆔 **ИНН:** {case['client_inn']}\n"
        if client_block:
            client_block += "\n"

    # --- Строка с источником ---
    if source_ok:
        source_line = f"🔗 {src_url}"
    else:
        source_line = "📄 По материалам пресс-службы Юго-Западного банка."

    content = TEMPLATES["case"].format(
        client_block=client_block,
        industry=case.get("industry", "—"),
        region=case.get("region", "—"),
        deal_type=case.get("deal_type", "—"),
        deal_amount=case.get("deal_amount", "—"),
        deal_term=case.get("deal_term", "—"),
        deal_place=case.get("deal_place", "—"),
        deal_period=case.get("deal_period", "—"),
        purpose=case.get("purpose", "—"),
        structure=case.get("structure", "—"),
        result=case.get("result", "—"),
        region_effect=case.get("region_effect", "—"),
        source_line=source_line,
        industry_tag=_industry_tag(case.get("industry", "")),
    )

    logger.debug(
        f"Выбран кейс: «{case.get('client_name', '—')}» "
        f"({case.get('industry', '—')}, {case.get('region', '—')}), "
        f"ссылка {'есть' if source_ok else 'отсутствует'}"
    )

    return {
        "title": f"Кейс: {case.get('industry', '')} в {case.get('region', '')}",
        "content": content,
        "source_url": src_url,
    }
# ================================================================
# АНАЛИТИКА
# ================================================================

def generate_analytics_post() -> Dict:
    """
    Формирует пост-аналитику из content/analytics.json.
    - Отбирает записи за текущий год.
    - Проверяет, что source_url реально открывается.
    - Если ссылка битая — выводит только текстовое название источника.
    """
    analytics = load_analytics()
    if not analytics:
        logger.error("Файл analytics.json пуст или не прошёл валидацию")
        return {
            "title": "Аналитика рынка",
            "content": (
                "📈 **Аналитика для крупного и среднего бизнеса**\n\n"
                "Данные временно недоступны.\n\n"
                "#Аналитика #БизнесЮга #СберЮЗБ"
            ),
            "source_url": "",
        }

    today = date.today()
    relevant = [a for a in analytics if a.get("year") == today.year]
    dropped = len(analytics) - len(relevant)

    if dropped > 0:
        logger.info(
            f"Аналитика: всего {len(analytics)}, за {today.year} год — "
            f"{len(relevant)}, отброшено по году — {dropped}"
        )

    if not relevant:
        logger.warning(
            f"Нет аналитики за {today.year} год — использую общий список"
        )
        relevant = analytics

    data = random.choice(relevant)

    # --- Проверка ссылки на первоисточник ---
    src_url = data.get("source_url", "").strip()
    source_ok = validate_source_url(src_url)
    if not source_ok:
        if src_url:
            logger.warning(
                f"Ссылка-источник не работает, скрываю: {src_url}"
            )
        src_url = ""

    # --- Строка с источником ---
    if source_ok:
        source_url_line = f"🔗 {src_url}"
    else:
        source_url_line = ""

    content = TEMPLATES["analytics"].format(
        content=data["content"],
        insight=data["insight"],
        source=data.get("source", "—"),
        source_url_line=source_url_line,
        industry_tag=_industry_tag(data.get("industry", "")),
    )

    logger.debug(
        f"Выбрана аналитика: {data.get('industry', '—')} "
        f"({data.get('source', '—')}), "
        f"ссылка {'есть' if source_ok else 'отсутствует'}"
    )

    return {
        "title": "Аналитика рынка",
        "content": content,
        "source_url": src_url,
    }
# ================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ================================================================

def generate_post() -> Dict:
    post_type = random.choices(
        ["news", "case", "analytics"],
        weights=[0.5, 0.3, 0.2],
        k=1,
    )[0]

    logger.info(f"Выбран тип поста: {post_type}")

    if post_type == "news":
        news = fetch_rss_news(limit_per_source=10)

        if not news:
            logger.warning(
                "Нет новостей за текущий период — переключаюсь на аналитику"
            )
            return generate_analytics_post()

        prioritized = [n for n in news if n.get("inn") or n.get("company")]

        if prioritized:
            logger.info(
                f"Новостей с ИНН/компанией: {len(prioritized)} "
                f"из {len(news)} — выбираю из приоритетных"
            )
            pool = prioritized
        else:
            logger.info(
                f"Новостей с деталями не найдено, "
                f"выбираю из общего пула ({len(news)})"
            )
            pool = news

        for item in random.sample(pool, min(5, len(pool))):
            logger.debug(
                f"Пробую новость: «{item['title'][:60]}» "
                f"({item['published_date']})"
            )
            post = generate_news_post_with_ai(item)
            if post:
                logger.info(
                    f"Пост сгенерирован из новости: «{item['title'][:60]}»"
                )
                return post
            logger.debug("GigaChat не справился, пробую следующую")

        logger.warning(
            "Все попытки генерации новостей провалились — "
            "переключаюсь на аналитику"
        )
        return generate_analytics_post()

    if post_type == "case":
        post = generate_case_post()
        if post:
            logger.info("Пост-кейс сгенерирован успешно")
            return post
        logger.warning("Нет актуальных кейсов — переключаюсь на аналитику")
        return generate_analytics_post()

    logger.info("Пост-аналитика сгенерирован")
    return generate_analytics_post()
