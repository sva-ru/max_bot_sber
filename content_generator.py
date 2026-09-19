import feedparser
import random
from typing import Optional, Dict, List
from gigachat_client import generate_text

RSS_SOURCES = [
        "https://sberbank.ru/ru/s_m_business/news/rss",
        "https://kuban.rbc.ru/rss",
        "https://rostov.rbc.ru/rss",
        "https://expertsouth.ru/rss/",
        "https://stav.aif.ru/rss",
        "https://rss.app/feeds/yIKJm4GFujhAvtwA.xml",
]

TEMPLATES = {
        "news": """📊 **{title}**

{summary}

🔗 Подробнее: {link}

#ЮгБизнес #СберЮЗБ #КрупныйБизнес""",

        "case": """💼 **Кейс клиента Юго-Западного банка**

{content}

📌 Отрасль: {industry}
📍 Регион: {region}

#КейсыКлиентов #СберЮЗБ #БизнесЮга""",

        "analytics": """📈 **Аналитика для крупного и среднего бизнеса**

{content}

🔍 Источник: {source}

#Аналитика #БизнесЮга #СберЮЗБ""",
}

def fetch_rss_news(limit_per_source: int = 3) -> List[Dict]:
        news_items = []
        for url in RSS_SOURCES:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:limit_per_source]:
                        news_items.append({
                                        "title": entry.get("title", ""),
                                        "summary": entry.get("summary", "")[:300],
                                        "link": entry.get("link", ""),
                                        "published": entry.get("published", ""),
                                        "source": url
                        })
                except Exception as e:
                    print(f"Ошибка загрузки RSS {url}: {e}")
        return news_items

def generate_news_post(news_item: Dict) -> Optional[Dict]:
        if not news_item.get("title"):
            return None
        content = TEMPLATES["news"].format(
            title=news_item["title"],
            summary=news_item.get("summary", "Подробности по ссылке."),
            link=news_item.get("link", "")
        )
        return {
                "title": news_item["title"],
                "content": content,
                "source_url": news_item.get("link", "")
        }

def generate_case_post() -> Dict:
        cases = [
                {
                        "industry": "АПК",
                        "region": "Краснодарский край",
                        "content": "Предприятие по глубокой переработке зерна получило возобновляемую кредитную линию на 1 млрд рублей для закупки сырья и модернизации производства. Финансирование открыто на три года с автоматической пролонгацией."
                },
                {
                        "industry": "Машиностроение",
                        "region": "Ростовская область",
                        "content": "«Ростсельмаш» получил банковскую гарантию на 4,2 млрд рублей для строительства нового завода по выпуску широкой линейки сельхозтехники."
                },
                {
                        "industry": "Туризм",
                        "region": "Республика Крым",
                        "content": "Крупный санаторно-курортный комплекс привлёк проектное финансирование для реконструкции номерного фонда и строительства СПА-центра. Срок окупаемости — 7 лет."
                }
        ]
        case = random.choice(cases)
        content = TEMPLATES["case"].format(**case)
        return {
                "title": f"Кейс: {case['industry']} в {case['region']}",
                "content": content,
                "source_url": ""
        }

def generate_analytics_post() -> Dict:
        analytics_data = [
                {
                        "content": "Портфель проектов Юго-Западного банка Сбербанка на Кубани достиг 239 млрд рублей. Лидеры по объёму: Краснодарский край (212 млрд), Ростовская область (11 млрд), Ставрополье (9 млрд).",
                        "source": "Пресс-служба Сбербанка, март 2025"
                },
                {
                        "content": "Кредитный портфель ЮЗБ в АПК превысил 350 млрд рублей. Приоритетные направления: интенсивное садоводство, глубокая переработка продукции, экспорт.",
                        "source": "Юго-Западный банк Сбербанка"
                },
                {
                        "content": "Более 185 компаний юга России проходят цифровую трансформацию с помощью акселератора DTaaS от Сбера. Участники — представители крупного и среднего бизнеса из Ростова, Краснодара, Ставрополя и Симферополя.",
                        "source": "Пресс-релиз Сбера"
                }
        ]
        data = random.choice(analytics_data)
        content = TEMPLATES["analytics"].format(**data)
        return {
                "title": "Аналитика рынка",
                "content": content,
                "source_url": ""
        }

def generate_post() -> Dict:
        post_type = random.choices(
                ["news", "case", "analytics"],
                weights=[0.6, 0.2, 0.2],
                k=1
        )[0]

        if post_type == "news":
                news = fetch_rss_news(limit_per_source=5)
                if news:
                        for item in random.sample(news, min(5, len(news))):
                            post = generate_news_post_with_gigachat(item)
                            if post:
                                return post
                return generate_analytics_post()
        elif post_type == "case":
                return generate_case_post()
        else:
                return generate_analytics_post()


def generate_news_post_with_gigachat(news_item: Dict) -> Optional[Dict]:
    """
    Генерирует пост на основе новости, используя GigaChat для перефразирования.
    """
    if not news_item.get("title"):
        return None

    prompt = f"""Ты — редактор делового канала «Бизнес-Фактор Юго-Запад» для клиентов крупного и среднего бизнеса Юго-Западного банка Сбербанка России.

Напиши пост на основе этой новости:
Заголовок: {news_item['title']}
Краткое содержание: {news_item.get('summary', '')}
Ссылка: {news_item.get('link', '')}

Требования:
1. Стиль: экспертный, деловой, но живой. Без «воды» и клише.
2. Структура: яркий заголовок с эмодзи (📊, 💼, 📈), 2-3 абзаца сути, вывод или рекомендация для бизнеса.
3. Добавь в конце 3-4 релевантных хэштега (например, #ЮгБизнес #СберЮЗБ #КрупныйБизнес).
4. Объем: не более 1500 символов.
5. Не упоминай, что текст сгенерирован ИИ.

Напиши только готовый текст поста, без пояснений.
"""
    generated = generate_text(prompt, temperature=0.7)

    if not generated:
        # Фолбэк на старый шаблонный метод
        return generate_news_post(news_item)

    return {
        "title": news_item["title"],
        "content": generated,
        "source_url": news_item.get("link", ""),
        "ai_generated": True
    }