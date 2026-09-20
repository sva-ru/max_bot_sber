# scheduler.py
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from config import TIMEZONE, POST_INTERVAL_HOURS
from publisher import publish_post

logger = logging.getLogger(__name__)


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        publish_post,
        trigger=IntervalTrigger(hours=POST_INTERVAL_HOURS),
        id="publish_post",
        name="Публикация в канал ЮЗБ Бизнес",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.add_job(
        publish_post,
        trigger=CronTrigger(hour=9, minute=0, timezone=TIMEZONE),
        id="morning_post",
        name="Утренняя публикация",
        replace_existing=True,
    )

    logger.info(
        f"Планировщик настроен: публикации каждые {POST_INTERVAL_HOURS} ч. "
        f"+ утренний пост в 9:00"
    )
    return scheduler
