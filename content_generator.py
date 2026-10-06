# content_generator.py
"""
Генератор контента для канала «Бизнес-Фактор Юго-Запад».

Публикуются ТОЛЬКО свежие новости из RSS и RSSHub.

Фильтры (в порядке применения):
1. Очистка HTML и отсев «плохих» заголовков.
2. По дате (DATE_FILTER: quarter / year / none).
3. Чёрный список — спорт, шоу-бизнес, погода, ЧС,
   политика, международка, макроэкономика США,
   ЧП, криминал, кадровые назначения, военные действия.
4. Региональная привязка — обязательна (кроме доверенных).
5. Белый список — бизнес-лексика (для нетрастевых источников).
6. GigaChat: если модель вернула blacklist или фразу-заглушку —
   новость пропускается, бот пробует следующую.

Логи идут ТОЛЬКО в stdout (файловое логирование отключено).
feedparser.parse вызывается асинхронно через asyncio.to_thread,
чтобы не блокировать event loop (важно для health-сервера).
"""
import asyncio
import html as html_module
import logging
import random
import re
from datetime import date, datetime
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse

import feedparser

from gigachat_client import generate_text_safe
from url_utils import resolve_url
from config import (
    DATE_FILTER,
    RSSHUB_ACCESS_KEY,
    RSSHUB_BASE_URL,
)

logger = logging.getLogger(__name__)


# ================================================================
# RSSHUB
# ================================================================

def rsshub_url(path: str) -> str:
    if not RSSHUB_BASE_URL or not RSSHUB_ACCESS_KEY:
        return ""
    path = path.lstrip("/")
    return f"{RSSHUB_BASE_URL}/{path}?key={RSSHUB_ACCESS_KEY}"


# ================================================================
# RSS-ИСТОЧНИКИ
# ================================================================

_STATIC_SOURCES = [
    "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "https://www.kommersant.ru/RSS/main.xml",
]

_RSSHUB_PATHS = [
    "telegram/channel/rbc_kavkaz",
    "telegram/channel/kavkaz_rf",
    "telegram/channel/GorodNRostov",
    "telegram/channel/atorus",
    "telegram/channel/expertsouth",
    "telegram/channel/agroinvestor",
    "telegram/channel/agrotrendru",
    "telegram/channel/mcx_ru",
    "telegram/channel/rbc_krasnodar",
    "telegram/channel/minec_tourism",
]

RSS_SOURCES = _STATIC_SOURCES + [
    url for url in (rsshub_url(p) for p in _RSSHUB_PATHS) if url
]


# ================================================================
# ОЧИСТКА HTML И ЗАГОЛОВКОВ
# ================================================================

_HTML_TAG = re.compile(r"<[^>]+>")
_MULTIPLE_SPACES = re.compile(r"[ \t]{2,}")
_MULTIPLE_NEWLINES = re.compile(r"\n{3,}")

DATE_ONLY_TITLE = re.compile(
    r"^\s*(?:"
    r"\d{1,2}\s+"
    r"(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*"
    r"(?:\s+\d{4})?"
    r"|понедельник|вторник|среда|четверг|пятница|суббота|воскресенье"
    r"|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}"
    r")\s*$",
    re.IGNORECASE,
)

MIN_TITLE_LENGTH = 15


def clean_html(text: str) -> str:
    """Убирает HTML-теги, декодирует сущности, чистит пробелы."""
    if not text:
        return ""

    text = re.sub(r"</(p|div|br|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = _HTML_TAG.sub("", text)
    text = html_module.unescape(text)
    text = _MULTIPLE_SPACES.sub(" ", text)
    text = _MULTIPLE_NEWLINES.sub("\n\n", text)

    return text.strip()


def is_meaningful_title(title: str) -> bool:
    """Отсеивает заголовки-даты, дни недели и слишком короткие."""
    if not title:
        return False
    t = title.strip()
    if len(t) < MIN_TITLE_LENGTH:
        return False
    if DATE_ONLY_TITLE.match(t):
        return False
    return True


# ================================================================
# ФРАЗЫ-ЗАГЛУШКИ GIGACHAT
# ================================================================

REFUSAL_PHRASES = [
    "к сожалению, иногда генеративные языковые модели",
    "временно ограничены",
    "не могу обсуждать эту тему",
    "давайте поговорим о другом",
    "я не могу помочь с этим запросом",
    "не могу предоставить ответ на этот вопрос",
    "извините, но я не могу",
]


def _is_refusal(text: str) -> bool:
    if not text:
        return True
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in REFUSAL_PHRASES)


# ================================================================
# ФИЛЬТР РЕЛЕВАНТНОСТИ
# ================================================================

TRUSTED_HOSTS = {
    "sberbank.ru",
    "www.sberbank.ru",
    "expertsouth.ru",
    "www.expertsouth.ru",
}

BLACKLIST_KEYWORDS = [
    # ================================================================
    # СПОРТ
    # ================================================================
    "теннис", "джокович", "надаль", "медведев выиграл",
    "atp ", "wta ", "атп ", "втб арена",
    "футбол", "рпл ", "кхл ", "нба ", "фифа", "уефа", "премьер-лига",
    "олимпиад", "олимпийск",
    "хокке", "баскетбол", "волейбол", "бокс", "ufc", "мма ",
    "формула-1", "гонк",
    "матч", "турнир", "полуфинал", "четвертьфинал", "чемпионат", "кубок",
    "зенит", "спартак", "цска", "динамо", "краснодар сыграл",

    # ================================================================
    # ШОУ-БИЗНЕС И РАЗВЛЕЧЕНИЯ
    # ================================================================
    "шоу-бизнес", "селебрити", "актер", "актрис", "актёр",
    "фильм вышел", "премьера фильма", "сериал", "концерт", "евровидение",
    "мисс вселенная", "блогер", "тиктокер", "инфлюенсер",

    # ================================================================
    # ПОГОДА И ЧС
    # ================================================================
    "циклон", "антициклон", "ураган", "наводнение", "землетрясение",
    "паводок", "штормовое предупреждение", "аномальная жара", "гололёд",

    # ================================================================
    # ЗДОРОВЬЕ, ЭЗОТЕРИКА
    # ================================================================
    "коронавирус", "covid", "вакцин", "эпидеми", "птичий грипп",
    "гороскоп", "астролог",

    # ================================================================
    # ПОЛИТИКА И МЕЖДУНАРОДКА
    # ================================================================
    "трамп", "байден", "путин", "зеленский", "макрон",
    "белый дом", "конгресс сша", "сенат сша", "госдеп",
    "сша", "америк", "евросоюз", "нато",
    "санкц", "эмбарго",
    "выборы", "предвыборн", "кандидат в президент",
    "госдума приняла", "законопроект", "поправк в закон",
    "минфин сша", "фрс ", "федеральная резервная",
    "опек", "оон", "брикс", "глобальн",

    # ================================================================
    # ГЛАВЫ РЕГИОНОВ ЮГА И ПОЛИТИЧЕСКИЕ МАРКЕРЫ
    # ================================================================
    "развожаев", "кондратьев", "голубев", "владимиров",
    "клычков", "мени", "кадыров", "калиматов",
    "глава региона", "губернатор", "мэр ", "депутат", "сенатор",
    "администрация президента", "правительство рф",
    "крымская ипотека", "льготная ипотека",

    # ================================================================
    # МАКРО БЕЗ ПРИВЯЗКИ
    # ================================================================
    "биткоин", "криптовалют", "эфириум",
    "нефть марки", "цена на нефть", "brent", "urals",
    "курс доллара", "курс евро", "ключевая ставка цб",
    "инфляция в россии", "ввп россии",

    # ================================================================
    # ЧП, ПРОИСШЕСТВИЯ, ЧС
    # ================================================================
    "пропал", "пропали", "пропавш", "разыскива", "исчез",
    "спасател", "мчс", "поисково-спасательн", "поиски",
    "сбил", "сбились", "заблудил",
    "аварийн", "отключени", "обесточ", "без света", "без электроэнерг",
    "чп ", "чс ", "происшеств", "катастроф", "трагед",
    "погиб", "погибл", "скончал", "умер ",
    "пожар", "взрыв", "дтп", "крушени", "авари",
    "наводнени", "обрушени", "прорыв",

    # ================================================================
    # КРИМИНАЛ
    # ================================================================
    "убийств", "убит", "ограблен", "разбойн", "похищен",
    "мошенник", "коррупц", "взятк", "хищен",
    "арестован", "задержан", "осужден", "приговор",
    "уголовн", "следственн", "прокуратур", "следком",
    "уклонение от налогов", "уклонился от",

    # ================================================================
    # ПОЛИТИКА И НАЗНАЧЕНИЯ
    # ================================================================
    "назначен", "назначени", "избран", "избрани",
    "возглавил", "врио", "и.о.", "исполняющий обязанност",
    "ушёл в отставку", "ушел в отставку", "покинул пост",
    "отставк", "кадровые изменени",
    "президент", "премьер-министр", "спикер", "вице-премьер",
    "министр", "заместитель министр", "парламент",
    "законодательн", "администрация район", "администрации город",

    # ================================================================
    # ВОЕННОЕ И ОБОРОННОЕ
    # ================================================================
    "вс ", "всу", "вооружен", "минобороны", "военн",
    "бпла", "дрон", "ракет", "обстрел", "удар ",
    "мобилизац", "сво ", "боев", "фронт", "оборон",
    "спецоперац",

    # ================================================================
    # ПРОЧЕЕ, НЕ СВЯЗАННОЕ С БИЗНЕСОМ
    # ================================================================
    "здравоохранен", "больниц", "госпитал",
    "школ", "детск", "вуз ", "образован",
]

REGIONAL_ANCHORS = [
    "краснодар", "кубан", "сочи", "новороссийск", "анап",
    "армавир", "геленджик", "туапсе",
    "ростов", "таганрог", "шахты", "новочеркасск", "волгодонск",
    "ставропол", "пятигорск", "кисловодск", "ессентуки", "георгиевск",
    "адыге", "майкоп", "калмык", "элист",
    "крым", "симферопол", "севастопол", "ялта", "керч", "феодоси",
    "евпатори", "саки", "судак", "алушт",
    "дагестан", "махачкал", "дербент", "каспийск",
    "чечн", "грозн",
    "кабард", "балкар", "нальчик",
    "осети", "владикавказ", "беслан",
    "ингушет", "магас", "назран",
    "карачаев", "черкесск",
    "северный кавказ", "северо-кавказск",
    "юг россии", "южный федеральный", "юфо", "скфо",
    "юго-западн", "юзб", "юго-западный банк",
]

WHITELIST_KEYWORDS = [
    "компани", "корпораци", "фирм", "предприят", "стартап", "предпринимател",
    "ооо ", "ао ", "пао ", "зао ", "бизнес", "мсп ", "малому и среднему",
    "крупному бизнесу",
    "инвестор", "инвестиц", "инвестпроект", "кредит", "заем", "заём",
    "финансировани", "банк", "сбер", "втб", "газпромбанк", "альфа-банк",
    "сделк", "контракт", "соглашени", "договор",
    "млрд", "млн", "миллиард", "миллион", "тыс. руб",
    "выручк", "прибыл", "оборот", "капитал", "налог", "субсиди",
    "льготн", "ставк", "акци", "облигац", "бирж",
    "апк", "агро", "сельхоз", "сельское хозяйство", "зерн", "молок",
    "птицевод", "тепличн", "машиностро", "металлург", "металлообработк",
    "станкостро", "туризм", "курорт", "гостин", "отел", "санатор",
    "логистик", "транспор", "склад", "строительств", "девелопер",
    "недвижимост", "ритейл", "торгов", "розничн", "оптов",
    "экспорт", "импорт", "внешнеэкономическа",
    "производств", "завод", "фабрик", "цех", "промышленн",
    "элеватор", "агрохолдинг", "птицефабрик", "молочн", "сыровар",
    "винодел", "виноград", "садовод", "виноградар",
    "комбайн", "трактор", "сельхозтехник", "спецтехник",
    "агропром", "агроэкспорт", "продовольствен",
    "рыболов", "рыбовод", "аквакультур",
    "порт", "терминал", "контейнер", "грузооборот",
    "госзакупк", "тендер", "аукцион", "закупк",
    "модернизац", "реконструкц", "капремонт",
    "франшиз", "маркетплейс",
    "газпром", "роснефт", "лукойл", "роснано", "ростех",
    "цифровизац", "it-", "ит-", "технологи", "инновац",
    "искусственный интеллект", "ии ",
    "господдержк", "нацпроект", "национальн проект", "гчп", "концесси",
    "особая экономическая зона", "тосэр", "резидент", "меры поддержки",
]


def _hostname(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _find_keyword(text_lower: str, keywords: list) -> Optional[str]:
    for kw in keywords:
        if kw in text_lower:
            return kw
    return None


def has_regional_anchor(text_lower: str) -> bool:
    return any(a in text_lower for a in REGIONAL_ANCHORS)


def is_relevant_news(text: str, source_url: str = "") -> Tuple[bool, str]:
    if not text or not text.strip():
        return False, "empty"

    text_lower = text.lower()

    hit = _find_keyword(text_lower, BLACKLIST_KEYWORDS)
    if hit:
        return False, f"blacklist:{hit}"

    if _hostname(source_url) in TRUSTED_HOSTS:
        return True, "trusted"

    if not has_regional_anchor(text_lower):
        return False, "no-region"

    hit = _find_keyword(text_lower, WHITELIST_KEYWORDS)
    if hit:
        return True, f"whitelist:{hit}"

    return False, "no-whitelist"


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
    if entry_date > today:
        return False
    if DATE_FILTER == "none":
        return True
    if entry_date.year != today.year:
        return False
    if DATE_FILTER == "year":
        return True
    return current_quarter(entry_date) == current_quarter(today)


# ================================================================
# ИЗВЛЕЧЕНИЕ ИНН / КОМПАНИЙ
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
# ШАБЛОН НОВОСТИ
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
}


# ================================================================
# АСИНХРОННЫЙ ПАРСИНГ ОДНОЙ ЛЕНТЫ
# ================================================================

async def _parse_feed_async(url: str):
    """
    Асинхронно парсит RSS-ленту через asyncio.to_thread,
    чтобы не блокировать event loop.
    """
    try:
        return await asyncio.to_thread(feedparser.parse, url)
    except Exception as e:
        logger.warning(f"Ошибка парсинга RSS {url}: {e}")
        return None


# ================================================================
# СБОР RSS
# ================================================================

async def fetch_rss_news(limit_per_source: int = 30) -> List[Dict]:
    news_items: List[Dict] = []
    today = date.today()
    q = current_quarter(today)

    stats = {
        "total": 0, "accepted": 0,
        "wrong_year": 0, "wrong_quarter": 0, "no_date": 0, "future": 0,
        "rej_blacklist": 0, "rej_no_region": 0, "rej_no_whitelist": 0,
        "bad_title": 0,
        "with_inn": 0, "with_company": 0,
    }

    rsshub_count = len([
        u for u in RSS_SOURCES
        if RSSHUB_BASE_URL and RSSHUB_BASE_URL in u
    ])
    logger.info(
        f"Начинаю сбор RSS. Фильтр дат: {DATE_FILTER}. "
        f"Период: {today.year} год, {q} квартал. "
        f"Источников: {len(RSS_SOURCES)} (из них RSSHub: {rsshub_count}). "
        f"Лимит с источника: {limit_per_source}"
    )

    for url in RSS_SOURCES:
        try:
            feed = await _parse_feed_async(url)
            if feed is None:
                logger.debug(f"[{url}] ошибка парсинга")
                continue

            src_total = len(feed.entries)
            src_accepted = 0
            src_wrong_year = 0
            src_wrong_quarter = 0
            src_no_date = 0
            src_future = 0
            src_irrelevant = 0
            src_bad_title = 0

            if src_total == 0:
                logger.warning(f"[{url}] лента пуста (0 записей)")
                continue

            logger.debug(f"--- Источник: {url} (всего {src_total}) ---")

            for entry in feed.entries:
                stats["total"] += 1
                entry_date = parse_entry_date(entry)

                raw_title = clean_html(entry.get("title", ""))
                raw_summary = clean_html(entry.get("summary", ""))[:700]
                raw_link = entry.get("link", "")
                title = raw_title[:80]

                if not is_meaningful_title(raw_title):
                    stats["bad_title"] += 1
                    src_bad_title += 1
                    logger.debug(f"[{url}] BAD_TITLE: «{raw_title}»")
                    continue

                if entry_date is None:
                    stats["no_date"] += 1
                    src_no_date += 1
                    logger.debug(f"[{url}] NO_DATE: «{title}»")
                    continue

                if entry_date > today:
                    stats["future"] += 1
                    src_future += 1
                    logger.debug(f"[{url}] FUTURE {entry_date.isoformat()}: «{title}»")
                    continue

                if DATE_FILTER in ("year", "quarter") and entry_date.year != today.year:
                    stats["wrong_year"] += 1
                    src_wrong_year += 1
                    logger.debug(f"[{url}] WRONG_YEAR {entry_date.year}: «{title}»")
                    continue

                if DATE_FILTER == "quarter" and current_quarter(entry_date) != q:
                    stats["wrong_quarter"] += 1
                    src_wrong_quarter += 1
                    logger.debug(
                        f"[{url}] WRONG_QUARTER Q{current_quarter(entry_date)}: «{title}»"
                    )
                    continue

                full_text = f"{title} {raw_summary}"
                is_rel, reason = is_relevant_news(full_text, source_url=url)
                if not is_rel:
                    src_irrelevant += 1
                    if reason.startswith("blacklist:"):
                        stats["rej_blacklist"] += 1
                    elif reason == "no-region":
                        stats["rej_no_region"] += 1
                    elif reason == "no-whitelist":
                        stats["rej_no_whitelist"] += 1
                    logger.debug(f"[{url}] IRRELEVANT {reason}: «{title}»")
                    continue

                stats["accepted"] += 1
                src_accepted += 1

                inn = extract_inn(full_text)
                company = extract_company_name(full_text)
                if inn:
                    stats["with_inn"] += 1
                if company:
                    stats["with_company"] += 1

                clean_link = resolve_url(raw_link, source_url=url)

                news_items.append({
                    "title": raw_title,
                    "summary": raw_summary,
                    "link": clean_link,
                    "raw_link": raw_link,
                    "published_date": entry_date.isoformat(),
                    "source": url,
                    "inn": inn,
                    "company": company,
                })

                logger.debug(
                    f"[{url}] ПРИНЯТО ({reason}): «{title}»"
                    + (f" | ИНН: {inn}" if inn else "")
                    + (f" | Компания: {company}" if company else "")
                )

                if src_accepted >= limit_per_source:
                    logger.debug(f"[{url}] достигнут лимит {limit_per_source}")
                    break

            logger.info(
                f"[{url}] всего {src_total} | принято {src_accepted} | "
                f"отброшено: год {src_wrong_year}, "
                f"квартал {src_wrong_quarter}, без даты {src_no_date}, "
                f"будущее {src_future}, "
                f"плохой заголовок {src_bad_title}, "
                f"нерелевантных {src_irrelevant}"
            )

        except Exception as e:
            logger.warning(f"Ошибка загрузки RSS {url}: {e}")

    rejected_count = stats["total"] - stats["accepted"]
    summary_text = (
        f"=== ИТОГ СБОРА RSS ===\n"
        f"  Всего записей: {stats['total']}\n"
        f"  Принято: {stats['accepted']} "
        f"(с ИНН: {stats['with_inn']}, с компанией: {stats['with_company']})\n"
        f"  Отброшено: {rejected_count}\n"
        f"    - не текущий год: {stats['wrong_year']}\n"
        f"    - не текущий квартал: {stats['wrong_quarter']}\n"
        f"    - без даты: {stats['no_date']}\n"
        f"    - из будущего: {stats['future']}\n"
        f"    - плохой заголовок: {stats['bad_title']}\n"
        f"    - чёрный список: {stats['rej_blacklist']}\n"
        f"    - нет региональной привязки: {stats['rej_no_region']}\n"
        f"    - нет бизнес-лексики: {stats['rej_no_whitelist']}\n"
        f"  Фильтр дат: {DATE_FILTER}. Период: {today.year} год, {q} квартал"
    )
    logger.info(summary_text)

    if stats["accepted"] == 0:
        logger.warning(
            f"ВНИМАНИЕ: ни одной новости не прошло фильтр. "
            f"Попробуйте ослабить фильтры или добавить источники."
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
# ГАРАНТИЯ ССЫЛКИ
# ================================================================

def _ensure_source_link(text: str, source_url: str) -> str:
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

async def generate_news_post_with_ai(news_item: Dict) -> Optional[Dict]:
    """
    Асинхронно генерирует пост через GigaChat.
    Пропускает новость, если:
      - GigaChat вернул пустой ответ;
      - finish_reason == 'blacklist';
      - в ответе есть фраза-заглушка;
      - модель вернула SKIP.
    """
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
Ссылка: {news_item.get('link', '')}
Дата публикации: {news_item.get('published_date', '—')}
Период: {period_line}

Известные факты о сделке/компании (только они достоверны):
{facts_block}

ПЕРВОЕ И ГЛАВНОЕ ПРАВИЛО — ПРОВЕРКА РЕЛЕВАНТНОСТИ:
Если новость НЕ относится к одной из тем:
  • бизнес, компании, предпринимательство;
  • экономика, финансы, банки, инвестиции;
  • промышленность, АПК, строительство, логистика, туризм;
  • развитие регионов Юга России и Северного Кавказа;
  • господдержка бизнеса, нацпроекты, ГЧП,
— то верни РОВНО одно слово: SKIP

НЕ пиши пост на темы: спорт, шоу-бизнес, погода и ЧС, происшествия, здоровье, политика и международка (США, ЕС, НАТО, санкции), макроэкономика без привязки к Югу России.

Остальные правила:
1. Период публикации — текущий год и текущий квартал.
2. ИНН и название компании упоминай ТОЛЬКО если они есть в блоке «Известные факты». Если блока нет — не выдумывай.
3. Никаких данных «по слухам» — только то, что есть в исходных данных.
4. Объём: 1000–1800 символов.
4a. В тексте поста НЕ должно быть HTML-тегов (<p>, <br>, <a>, <b> и т. п.).
    Если в исходных данных есть теги — удали их.
5. Структура:
   • Заголовок начинай РОВНО с одного эмодзи из набора: 📊 💼 📈 🏭.
   • Абзац 1 — суть: что произошло, кто участники, где, когда.
   • Абзац 2 — детали: суммы, условия, сроки, отрасли, регионы.
   • Абзац 3 — «Что это значит для бизнеса Юга России»: практический вывод.
6. НЕ добавляй хэштеги — они будут добавлены автоматически.
7. Не упоминай, что текст сгенерирован ИИ.

Выведи только готовый текст поста или одно слово SKIP.
"""

    generated, finish_reason = await generate_text_safe(prompt, retries=2)

    if not generated:
        logger.info(
            f"GigaChat вернул пустой ответ (reason={finish_reason}) "
            f"для «{news_item['title'][:60]}» — пропуск"
        )
        return None

    if finish_reason == "blacklist":
        logger.warning(
            f"GigaChat: тематическое ограничение (blacklist) "
            f"для «{news_item['title'][:60]}» — пропуск"
        )
        return None

    if _is_refusal(generated):
        logger.warning(
            f"GigaChat вернул фразу-заглушку "
            f"для «{news_item['title'][:60]}» — пропуск"
        )
        return None

    if generated.strip().upper() == "SKIP":
        logger.info(f"GigaChat вернул SKIP: «{news_item['title'][:60]}»")
        return None

    generated = clean_html(generated)

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
# ГЛАВНАЯ ФУНКЦИЯ
# ================================================================

async def generate_post() -> Optional[Dict]:
    """
    Асинхронно возвращает готовый пост (новость)
    или None, если ничего не подошло.
    """
    logger.info("Собираю свежие новости...")
    news = await fetch_rss_news(limit_per_source=30)

    if not news:
        logger.warning("Нет новостей, прошедших фильтры. Публикация отменена.")
        return None

    logger.info(f"Доступно новостей: {len(news)}")

    sample_size = min(25, len(news))
    for item in random.sample(news, sample_size):
        logger.debug(
            f"Пробую: «{item['title'][:60]}» ({item['published_date']})"
        )
        post = await generate_news_post_with_ai(item)
        if post:
            logger.info(f"Пост сгенерирован: «{item['title'][:60]}»")
            return post
        logger.debug("GigaChat вернул SKIP, отказ или ошибку — пробую следующую")

    logger.warning("Все попытки генерации провалились — публикация отменена")
    return None