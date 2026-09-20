# content_generator.py
import logging
import random
import re
from datetime import date, datetime
from typing import Optional, Dict, List

import feedparser

from gigachat_client import generate_text_safe
from url_utils import resolve_url

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
        "🔗 Источник:\n{source}\n\n"
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
    if not CASES:
        logger.warning("Список CASES пуст")
        return None

    today = date.today()
    relevant = [c for c in CASES if c.get("year") == today.year]
    dropped = len(CASES) - len(relevant)

    if dropped > 0:
        logger.info(
            f"Кейсы: всего {len(CASES)}, за {today.year} год — "
            f"{len(relevant)}, отброшено по году — {dropped}"
        )

    if not relevant:
        logger.warning(f"Нет кейсов за {today.year} год — рубрика пропущена")
        return None

    case = random.choice(relevant)

    client_block = ""
    if case.get("client_name") and case.get("source_url"):
        client_block += f"🏢 **Клиент:** {case['client_name']}\n"
    if case.get("client_inn") and case.get("source_url"):
        client_block += f"🆔 **ИНН:** {case['client_inn']}\n"
    if client_block:
        client_block += "\n"

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
        source_url=case.get("source_url", "—"),
        industry_tag=_industry_tag(case.get("industry", "")),
    )
    logger.debug(
        f"Выбран кейс: «{case.get('client_name', '—')}» "
        f"({case.get('industry', '—')}, {case.get('region', '—')})"
    )
    return {
        "title": f"Кейс: {case.get('industry', '')} в {case.get('region', '')}",
        "content": content,
        "source_url": case.get("source_url", ""),
    }


# ================================================================
# АНАЛИТИКА
# ================================================================

def generate_analytics_post() -> Dict:
    today = date.today()
    relevant = [a for a in ANALYTICS if a.get("year") == today.year]
    dropped = len(ANALYTICS) - len(relevant)

    if dropped > 0:
        logger.info(
            f"Аналитика: всего {len(ANALYTICS)}, за {today.year} год — "
            f"{len(relevant)}, отброшено по году — {dropped}"
        )

    if not relevant:
        logger.warning(
            f"Нет аналитики за {today.year} год — использую общий список"
        )
        relevant = ANALYTICS

    data = random.choice(relevant)
    content = TEMPLATES["analytics"].format(
        content=data["content"],
        insight=data["insight"],
        source=data.get("source", "—"),
        industry_tag=_industry_tag(data.get("industry", "")),
    )
    return {
        "title": "Аналитика рынка",
        "content": content,
        "source_url": data.get("source", ""),
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


# ================================================================
# ДАННЫЕ: КЕЙСЫ И АНАЛИТИКА
# ================================================================

CASES = [
    {
        "year": 2026,
        "client_name": "ООО «Кубань-Агро»",
        "client_inn": "2312345678",
        "industry": "АПК",
        "region": "Краснодарский край",
        "deal_type": "Возобновляемая кредитная линия",
        "deal_amount": "1 млрд рублей",
        "deal_term": "3 года с автоматической пролонгацией",
        "deal_place": "г. Краснодар, ул. Красная, 100, офис Юго-Западного банка",
        "deal_period": f"I квартал {datetime.now().year} года",
        "purpose": (
            "Закупка сырья для обеспечения непрерывного цикла переработки, "
            "а также модернизация производственной линии по глубокой "
            "переработке зерна."
        ),
        "structure": (
            "Транш-кредитование с возможностью выбора процентной ставки "
            "(фиксированная или плавающая). Обеспечение — залог "
            "производственного оборудования и поручительство материнской "
            "компании."
        ),
        "result": (
            "Увеличение мощности переработки на 40%, рост выручки на 22%, "
            "выход на экспортные рынки Ближнего Востока и Азии."
        ),
        "region_effect": (
            "Создано 120 новых рабочих мест, увеличены налоговые поступления "
            "в бюджет края, укреплены экспортные позиции региона."
        ),
        "source_url": "https://пример-пресс-релиза.ru/kuban-agro-2026",
    },
    {
        "year": 2026,
        "client_name": "АО «Ростсельмаш»",
        "client_inn": "6161234567",
        "industry": "Машиностроение",
        "region": "Ростовская область",
        "deal_type": "Банковская гарантия",
        "deal_amount": "4,2 млрд рублей",
        "deal_term": "24 месяца",
        "deal_place": "г. Ростов-на-Дону, ул. Большая Садовая, 45",
        "deal_period": f"I квартал {datetime.now().year} года",
        "purpose": (
            "Обеспечение исполнения контрактов при строительстве нового "
            "завода по выпуску широкой линейки сельхозтехники."
        ),
        "structure": (
            "Безотзывная банковская гарантия с возможностью пролонгации. "
            "Обеспечение — поручительство головной компании группы."
        ),
        "result": (
            "Создано 500 рабочих мест, локализация производства достигла 80%, "
            "запущены поставки в 12 регионов России."
        ),
        "region_effect": (
            "Ростовская область укрепила статус центра российского "
            "сельхозмашиностроения, выросли смежные производства."
        ),
        "source_url": "https://пример-пресс-релиза.ru/rostselmash-2026",
    },
    {
        "year": 2026,
        "client_name": "ООО «Крым-Курорт»",
        "client_inn": "9101234567",
        "industry": "Туризм",
        "region": "Республика Крым",
        "deal_type": "Проектное финансирование",
        "deal_amount": "2,8 млрд рублей",
        "deal_term": "7 лет",
        "deal_place": "г. Симферополь, пр. Кирова, 12, офис ЮЗБ",
        "deal_period": f"I квартал {datetime.now().year} года",
        "purpose": (
            "Реконструкция номерного фонда санаторно-курортного комплекса "
            "и строительство нового СПА-центра."
        ),
        "structure": (
            "Проектное финансирование с графиком выборки под этапы "
            "строительства. Обеспечение — залог земельного участка и "
            "будущих объектов недвижимости."
        ),
        "result": (
            "Увеличение номерного фонда на 180 мест, рост загрузки на 25% "
            "в сезон."
        ),
        "region_effect": (
            "Рост турпотока в регионе, развитие малого бизнеса вокруг "
            "курорта (питание, экскурсии, транспорт)."
        ),
        "source_url": "https://пример-пресс-релиза.ru/crimea-kurort-2026",
    },
]


ANALYTICS = [
    {
        "year": 2026,
        "industry": "АПК",
        "content": (
            f"Портфель проектов Юго-Западного банка Сбербанка на Кубани "
            f"достиг 239 млрд рублей по итогам I квартала "
            f"{datetime.now().year} года. Лидеры по объёму: Краснодарский "
            f"край (212 млрд), Ростовская область (11 млрд), Ставрополье "
            f"(9 млрд). Приоритетные направления — интенсивное садоводство, "
            f"глубокая переработка продукции и экспорт."
        ),
        "insight": (
            "Компаниям из Ростовской области и Ставрополья стоит активнее "
            "использовать инструменты банка — потенциал роста портфеля в этих "
            "регионах ещё не раскрыт. Особенно перспективны проекты, "
            "ориентированные на экспорт."
        ),
        "source": f"Пресс-служба Сбербанка, I квартал {datetime.now().year}",
    },
    {
        "year": 2026,
        "industry": "Цифровизация",
        "content": (
            f"Более 185 компаний юга России проходят цифровую трансформацию "
            f"с помощью акселератора DTaaS от Сбера по состоянию на "
            f"I квартал {datetime.now().year} года. Участники — "
            f"представители крупного и среднего бизнеса из Ростова-на-Дону, "
            f"Краснодара, Ставрополя и Симферополя."
        ),
        "insight": (
            "Цифровизация процессов сокращает издержки на 15–20% в первый "
            "год. Стоит рассмотреть участие в следующей волне акселератора — "
            "это бесплатно и даёт доступ к экспертизе Сбера."
        ),
        "source": f"Пресс-релиз Сбера, {datetime.now().year}",
    },
    {
        "year": 2026,
        "industry": "Туризм",
        "content": (
            f"Туристический поток на Юг России в I квартале "
            f"{datetime.now().year} года вырос на 18% год к году. "
            f"Краснодарский край, Крым и Ставрополье — лидеры по числу "
            f"размещённых туристов."
        ),
        "insight": (
            "Инвесторам в туристическую инфраструктуру стоит рассмотреть "
            "проектное финансирование — ставки по таким проектам "
            "субсидируются в рамках госпрограммы развития туризма."
        ),
        "source": f"Аналитика Ростуризма, I квартал {datetime.now().year}",
    },
]