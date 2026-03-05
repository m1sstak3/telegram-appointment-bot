"""
My appointments handler — client can view and cancel upcoming bookings.
Cancellation allowed only ≥3 days before appointment (PRD requirement).
"""

from __future__ import annotations

from datetime import UTC

import pytz
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from config import get_settings
from database import get_session
from keyboards.client import cancel_confirm_keyboard, my_appointments_keyboard
from models import Appointment, AppointmentStatus, User
from services.booking_service import CancelTooLateError, cancel_appointment_by_client
from sqlalchemy import select
from sqlalchemy.orm import selectinload

router = Router()
settings = get_settings()
MSK = pytz.timezone("Europe/Moscow")


def _fmt_msk(dt_utc) -> str:
    aware = dt_utc.replace(tzinfo=UTC)
    return aware.astimezone(MSK).strftime("%d.%m.%Y %H:%M")


@router.message(Command("my_appointments"))
async def my_appointments_command(message: Message) -> None:
    tg_id = message.from_user.id

    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        db_user: User | None = result.scalar_one_or_none()
        if not db_user:
            await message.answer("Сначала выполните /start")
            return

        appts_result = await session.execute(
            select(Appointment)
            .options(
                selectinload(Appointment.specialist),
                selectinload(Appointment.service),
            )
            .where(
                Appointment.user_id == db_user.id,
                Appointment.status.in_(
                    [AppointmentStatus.CONFIRMED, AppointmentStatus.RESCHEDULED]
                ),
            )
            .order_by(Appointment.scheduled_at)
        )
        appts = appts_result.scalars().all()

    if not appts:
        await message.answer(
            "📭 У вас нет активных записей.\n\nЗапишитесь через /start"
        )
        return

    lines = ["🗓 *Ваши предстоящие записи:*\n"]
    for appt in appts:
        lines.append(
            f"*#{appt.id}* — {appt.service.name}\n"
            f"   👨‍⚕️ {appt.specialist.name}\n"
            f"   📅 {_fmt_msk(appt.scheduled_at)} МСК\n"
        )

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=my_appointments_keyboard(appts),
    )


@router.callback_query(F.data == "my_appts:list")
async def my_appointments_list(call: CallbackQuery) -> None:
    await call.answer()
    tg_id = call.from_user.id

    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        db_user: User | None = result.scalar_one_or_none()
        if not db_user:
            await call.answer("Сначала выполните /start", show_alert=True)
            return

        appts_result = await session.execute(
            select(Appointment)
            .options(
                selectinload(Appointment.specialist),
                selectinload(Appointment.service),
            )
            .where(
                Appointment.user_id == db_user.id,
                Appointment.status.in_(
                    [AppointmentStatus.CONFIRMED, AppointmentStatus.RESCHEDULED]
                ),
            )
            .order_by(Appointment.scheduled_at)
        )
        appts = appts_result.scalars().all()

    if not appts:
        await call.message.edit_text(
            "📭 У вас нет активных записей.\n\nЗапишитесь через /start"
        )
        return

    lines = ["🗓 *Ваши предстоящие записи:*\n"]
    for appt in appts:
        lines.append(
            f"*#{appt.id}* — {appt.service.name}\n"
            f"   👨‍⚕️ {appt.specialist.name}\n"
            f"   📅 {_fmt_msk(appt.scheduled_at)} МСК\n"
        )

    await call.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=my_appointments_keyboard(appts),
    )


@router.callback_query(F.data.startswith("cancel_appt:"))
async def ask_cancel_confirmation(call: CallbackQuery) -> None:
    await call.answer()
    appt_id = int(call.data.split(":")[1])
    await call.message.edit_text(
        f"❓ Вы уверены, что хотите отменить запись *#{appt_id}*?\n\n"
        f"⚠️ Отмена возможна не позднее чем за 3 дня до визита.",
        parse_mode="Markdown",
        reply_markup=cancel_confirm_keyboard(appt_id),
    )


@router.callback_query(F.data.startswith("cancel_confirm:"))
async def do_cancel(call: CallbackQuery) -> None:
    appt_id = int(call.data.split(":")[1])
    tg_id = call.from_user.id

    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        db_user: User | None = result.scalar_one_or_none()
        if not db_user:
            await call.answer("Ошибка. Попробуйте /start", show_alert=True)
            return

        try:
            await cancel_appointment_by_client(
                session,
                appointment_id=appt_id,
                user_id=db_user.id,
                min_cancel_hours=settings.min_cancel_hours,
            )
        except CancelTooLateError:
            await call.message.edit_text(
                "⚠️ *Отмена невозможна*\n\n"
                "До визита осталось менее 3 дней. "
                "Пожалуйста, свяжитесь с администратором.",
                parse_mode="Markdown",
            )
            await call.answer()
            return
        except ValueError as e:
            await call.answer(str(e), show_alert=True)
            return

    # Remove reminder job if any
    from scheduler.reminders import cancel_reminder

    cancel_reminder(appt_id)

    await call.message.edit_text(
        f"✅ Запись *#{appt_id}* отменена.\n\nМожете записаться снова — /start",
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "cancel_abort")
async def cancel_abort(call: CallbackQuery) -> None:
    await my_appointments_list(call)
