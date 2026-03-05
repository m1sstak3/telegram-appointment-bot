"""
APScheduler — 24-hour reminder jobs and reminder lifecycle management.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import get_settings

if TYPE_CHECKING:
    from aiogram import Bot
    from models import Appointment, User

_settings = get_settings()

# Convert async SQLite URL to sync SQLite URL for APScheduler
sync_db_url = _settings.database_url.replace("sqlite+aiosqlite", "sqlite", 1)

# Module-level scheduler instance (configured in bot.py)
scheduler = AsyncIOScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=sync_db_url)},
    timezone="UTC",
)

_bot_ref: Bot | None = None


def set_bot(bot: Bot) -> None:
    """Call once at startup to give the scheduler access to the bot."""
    global _bot_ref
    _bot_ref = bot


# ─── Job function ──────────────────────────────────────────────────────────────


async def _send_reminder(
    telegram_id: int,
    appt_id: int,
    specialist_name: str,
    service_name: str,
    scheduled_at_utc: datetime,
) -> None:
    """Async job executed by APScheduler — sends the 24h reminder."""
    if _bot_ref is None:
        return
    import pytz

    MSK = pytz.timezone("Europe/Moscow")
    aware = scheduled_at_utc.replace(tzinfo=UTC)
    msk_str = aware.astimezone(MSK).strftime("%d.%m.%Y %H:%M")

    text = (
        f"⏰ *Напоминание о записи*\n\n"
        f"Завтра у вас визит к специалисту!\n\n"
        f"👨‍⚕️ *{specialist_name}*\n"
        f"💼 {service_name}\n"
        f"📅 *{msk_str} МСК*\n\n"
        f"Ждём вас! Если не сможете — пожалуйста, отмените запись заранее /my\\_appointments"
    )
    try:
        await _bot_ref.send_message(telegram_id, text, parse_mode="Markdown")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to send reminder to user %s: %s", telegram_id, e)


# ─── Public API ────────────────────────────────────────────────────────────────


def schedule_reminder(appt: Appointment, user: User) -> None:
    """Schedule a 24-hour reminder. Stores job_id on the appointment object."""
    fire_at = appt.scheduled_at - timedelta(hours=24)
    now_utc = datetime.now(UTC).replace(tzinfo=None)

    if fire_at <= now_utc:
        # Less than 24h away — don't schedule (appointment is too soon)
        return

    job_id = f"reminder_{appt.id}"
    # Remove existing job first (in case of reschedule)
    _safe_remove(job_id)

    scheduler.add_job(
        _send_reminder,
        trigger="date",
        run_date=fire_at,
        id=job_id,
        kwargs={
            "telegram_id": user.telegram_id,
            "appt_id": appt.id,
            "specialist_name": appt.specialist.name,
            "service_name": appt.service.name,
            "scheduled_at_utc": appt.scheduled_at,
        },
        replace_existing=True,
    )

    # Persist job_id back to DB (fire and forget — non-critical)
    import asyncio

    asyncio.create_task(_save_job_id(appt.id, job_id))


def cancel_reminder(appt_id: int) -> None:
    _safe_remove(f"reminder_{appt_id}")


def _safe_remove(job_id: str) -> None:
    try:
        scheduler.remove_job(job_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to remove job %s: %s", job_id, e)


async def _save_job_id(appt_id: int, job_id: str) -> None:
    from database import get_session
    from models import Appointment

    async with get_session() as session:
        appt = await session.get(Appointment, appt_id)
        if appt:
            appt.reminder_job_id = job_id
