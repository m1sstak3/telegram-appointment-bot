"""
Notification service: sends Telegram messages to clients on booking events.
All times displayed in Moscow timezone (UTC+3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytz
from aiogram import Bot

if TYPE_CHECKING:
    from models import Appointment, User

MSK = pytz.timezone("Europe/Moscow")


def _fmt_msk(dt_utc: datetime) -> str:
    aware = dt_utc.replace(tzinfo=UTC)
    return aware.astimezone(MSK).strftime("%d.%m.%Y %H:%M")


async def send_booking_confirmation(
    bot: Bot, user: User, appt: Appointment
) -> None:
    text = (
        f"✅ *Запись подтверждена!*\n\n"
        f"👨‍⚕️ Специалист: *{appt.specialist.name}*\n"
        f"💼 Услуга: *{appt.service.name}*\n"
        f"📅 Дата и время: *{_fmt_msk(appt.scheduled_at)} МСК*\n\n"
        f"🆔 Номер записи: `#{appt.id}`\n\n"
        f"Для отмены используйте команду /my\\_appointments\n"
        f"_(отмена возможна не позднее чем за 3 дня до визита)_"
    )
    try:
        await bot.send_message(user.telegram_id, text, parse_mode="Markdown")
    except Exception:
        pass  # user may have blocked bot


async def send_reminder(bot: Bot, user: User, appt: Appointment) -> None:
    text = (
        f"⏰ *Напоминание о записи*\n\n"
        f"Завтра у вас запись к специалисту!\n\n"
        f"👨‍⚕️ *{appt.specialist.name}*\n"
        f"💼 {appt.service.name}\n"
        f"📅 *{_fmt_msk(appt.scheduled_at)} МСК*\n\n"
        f"Ждём вас! Если не сможете прийти — пожалуйста, отмените запись заранее."
    )
    try:
        await bot.send_message(user.telegram_id, text, parse_mode="Markdown")
    except Exception:
        pass


async def send_reschedule_notice(bot: Bot, user: User, appt: Appointment) -> None:
    text = (
        f"🔄 *Ваша запись перенесена*\n\n"
        f"Администратор перенёс вашу запись на новое время.\n\n"
        f"👨‍⚕️ Специалист: *{appt.specialist.name}*\n"
        f"💼 Услуга: *{appt.service.name}*\n"
        f"📅 Новое время: *{_fmt_msk(appt.scheduled_at)} МСК*\n\n"
        f"Если новое время вам не подходит, свяжитесь с нами."
    )
    try:
        await bot.send_message(user.telegram_id, text, parse_mode="Markdown")
    except Exception:
        pass


async def send_cancel_notice(
    bot: Bot, user: User, appt: Appointment, reason: str = ""
) -> None:
    reason_line = f"\n📝 Причина: _{reason}_" if reason else ""
    text = (
        f"❌ *Ваша запись отменена*\n\n"
        f"Администратор отменил вашу запись.\n\n"
        f"👨‍⚕️ Специалист: *{appt.specialist.name}*\n"
        f"💼 Услуга: *{appt.service.name}*\n"
        f"📅 Дата: *{_fmt_msk(appt.scheduled_at)} МСК*"
        f"{reason_line}\n\n"
        f"Вы можете записаться снова — /start"
    )
    try:
        await bot.send_message(user.telegram_id, text, parse_mode="Markdown")
    except Exception:
        pass
