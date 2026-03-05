"""
Admin — appointments management.
View all appointments, reschedule, cancel (with client notification).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytz
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from config import get_settings
from database import get_session
from keyboards.admin import (
    appointment_actions_keyboard,
    appointments_filter_keyboard,
    appointments_list_keyboard,
    reschedule_date_select_keyboard,
    reschedule_time_select_keyboard,
)
from models import Appointment, AppointmentStatus
from services.booking_service import (
    SlotTakenError,
    cancel_appointment_by_admin,
    msk_str_to_utc,
    reschedule_appointment,
)
from services.notification_service import send_cancel_notice, send_reschedule_notice
from services.slot_service import get_available_dates, get_free_slots_for_date
from sqlalchemy import select
from sqlalchemy.orm import selectinload

router = Router()
settings = get_settings()
MSK = pytz.timezone("Europe/Moscow")


def _fmt_msk(dt_utc) -> str:
    aware = dt_utc.replace(tzinfo=UTC)
    return aware.astimezone(MSK).strftime("%d.%m.%Y %H:%M")


class AdminRescheduleFSM(StatesGroup):
    ChooseDate = State()
    ChooseTime = State()
    WaitCancelReason = State()


# ─── Filter menu ──────────────────────────────────────────────────────────────


@router.callback_query(F.data == "admin:appointments")
async def admin_appointments(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "📋 *Записи*\n\nВыберите фильтр:",
        parse_mode="Markdown",
        reply_markup=appointments_filter_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("appt_filter:"))
async def show_appointments(call: CallbackQuery, state: FSMContext) -> None:
    filter_key = call.data.split(":")[1]
    async with get_session() as session:
        q = select(Appointment).options(
            selectinload(Appointment.specialist),
            selectinload(Appointment.service),
            selectinload(Appointment.user),
        )
        if filter_key == "upcoming":
            q = q.where(
                Appointment.status.in_(
                    [AppointmentStatus.CONFIRMED, AppointmentStatus.RESCHEDULED]
                ),
                Appointment.scheduled_at >= datetime.utcnow(),
            )
        elif filter_key == "confirmed":
            q = q.where(Appointment.status == AppointmentStatus.CONFIRMED)
        elif filter_key == "cancelled":
            q = q.where(Appointment.status == AppointmentStatus.CANCELLED)
        elif filter_key == "all":
            q = q.where(Appointment.status != AppointmentStatus.CANCELLED)
        q = q.order_by(Appointment.scheduled_at.desc())
        result = await session.execute(q)
        appts = result.scalars().all()

    await state.update_data(current_filter=filter_key, appt_page=0)

    if not appts:
        await call.message.edit_text(
            "📭 Записей по выбранному фильтру нет.",
            reply_markup=appointments_filter_keyboard(),
        )
        await call.answer()
        return

    await call.message.edit_text(
        f"📋 Найдено записей: *{len(appts)}*",
        parse_mode="Markdown",
        reply_markup=appointments_list_keyboard(appts, page=0),
    )
    await call.answer()


@router.callback_query(F.data.startswith("appt_page:"))
async def paginate_appointments(call: CallbackQuery, state: FSMContext) -> None:
    page = int(call.data.split(":")[1])
    data = await state.get_data()
    filter_key = data.get("current_filter", "all")
    # Reload and paginate
    async with get_session() as session:
        q = select(Appointment).options(
            selectinload(Appointment.specialist),
            selectinload(Appointment.service),
        )
        if filter_key == "upcoming":
            q = q.where(
                Appointment.status.in_(
                    [AppointmentStatus.CONFIRMED, AppointmentStatus.RESCHEDULED]
                ),
                Appointment.scheduled_at >= datetime.utcnow(),
            )
        elif filter_key == "confirmed":
            q = q.where(Appointment.status == AppointmentStatus.CONFIRMED)
        elif filter_key == "cancelled":
            q = q.where(Appointment.status == AppointmentStatus.CANCELLED)
        elif filter_key == "all":
            q = q.where(Appointment.status != AppointmentStatus.CANCELLED)
        q = q.order_by(Appointment.scheduled_at.desc())
        result = await session.execute(q)
        appts = result.scalars().all()
    await call.message.edit_reply_markup(
        reply_markup=appointments_list_keyboard(appts, page=page)
    )
    await call.answer()


# ─── Appointment detail ────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("admin_appt:"))
async def appointment_detail(call: CallbackQuery) -> None:
    appt_id = int(call.data.split(":")[1])
    async with get_session() as session:
        result = await session.execute(
            select(Appointment)
            .options(
                selectinload(Appointment.specialist),
                selectinload(Appointment.service),
                selectinload(Appointment.user),
            )
            .where(Appointment.id == appt_id)
        )
        appt: Appointment | None = result.scalar_one_or_none()

    if not appt:
        await call.answer("Запись не найдена.", show_alert=True)
        return

    status_map = {
        AppointmentStatus.CONFIRMED: "✅ Подтверждена",
        AppointmentStatus.RESCHEDULED: "🔄 Перенесена",
        AppointmentStatus.CANCELLED: "❌ Отменена",
        AppointmentStatus.PENDING: "⏳ Ожидает",
    }
    text = (
        f"📋 *Запись #{appt.id}*\n\n"
        f"👤 Клиент: {appt.user.full_name} (@{appt.user.username or '—'})\n"
        f"   📞 {appt.user.phone or '—'}\n\n"
        f"👨‍⚕️ Специалист: *{appt.specialist.name}*\n"
        f"💼 Услуга: *{appt.service.name}*\n"
        f"📅 Время: *{_fmt_msk(appt.scheduled_at)} МСК*\n"
        f"📌 Статус: {status_map.get(appt.status, appt.status)}\n"
    )
    if appt.cancel_reason:
        text += f"📝 Причина: _{appt.cancel_reason}_\n"

    await call.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=appointment_actions_keyboard(appt.id),
    )
    await call.answer()


# ─── Reschedule ────────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("admin_reschedule:"))
async def admin_reschedule_start(call: CallbackQuery, state: FSMContext) -> None:
    appt_id = int(call.data.split(":")[1])
    async with get_session() as session:
        result = await session.execute(
            select(Appointment)
            .options(
                selectinload(Appointment.specialist), selectinload(Appointment.service)
            )
            .where(Appointment.id == appt_id)
        )
        appt: Appointment | None = result.scalar_one_or_none()
        if not appt:
            await call.answer("Запись не найдена.", show_alert=True)
            return

        available_dates = await get_available_dates(
            session, appt.specialist_id, appt.service_id, settings.booking_horizon_days
        )

    await state.update_data(
        reschedule_appt_id=appt_id,
        reschedule_specialist_id=appt.specialist_id,
        reschedule_service_id=appt.service_id,
    )
    await state.set_state(AdminRescheduleFSM.ChooseDate)

    await call.message.edit_text(
        f"🔄 Перенос записи *#{appt_id}*\n\n📅 Выберите новую дату:",
        parse_mode="Markdown",
        reply_markup=reschedule_date_select_keyboard(
            available_dates, appt.specialist_id
        ),
    )
    await call.answer()


@router.callback_query(
    AdminRescheduleFSM.ChooseDate, F.data.startswith("reschedule_date:")
)
async def admin_reschedule_pick_time(call: CallbackQuery, state: FSMContext) -> None:
    chosen_date_str = call.data.split(":")[1]
    data = await state.get_data()

    async with get_session() as session:
        slots = await get_free_slots_for_date(
            session,
            data["reschedule_specialist_id"],
            data["reschedule_service_id"],
            date.fromisoformat(chosen_date_str),
        )

    if not slots:
        await call.answer("Нет свободных слотов на эту дату.", show_alert=True)
        return

    await state.update_data(reschedule_date=chosen_date_str)
    await state.set_state(AdminRescheduleFSM.ChooseTime)

    await call.message.edit_text(
        f"🔄 Выберите новое время ({chosen_date_str}):",
        reply_markup=reschedule_time_select_keyboard(slots, data["reschedule_appt_id"]),
    )
    await call.answer()


@router.callback_query(
    AdminRescheduleFSM.ChooseTime, F.data.startswith("reschedule_time:")
)
async def admin_reschedule_confirm(call: CallbackQuery, state: FSMContext) -> None:
    chosen_time = call.data.split(":", 1)[1]
    data = await state.get_data()
    appt_id = data["reschedule_appt_id"]

    new_utc = msk_str_to_utc(data["reschedule_date"], chosen_time)

    async with get_session() as session:
        try:
            await reschedule_appointment(
                session, appt_id, new_utc, data["reschedule_specialist_id"]
            )
        except SlotTakenError:
            await call.answer("Этот слот уже занят!", show_alert=True)
            return

        # Reload for notification
        result = await session.execute(
            select(Appointment)
            .options(
                selectinload(Appointment.specialist),
                selectinload(Appointment.service),
                selectinload(Appointment.user),
            )
            .where(Appointment.id == appt_id)
        )
        appt_full = result.scalar_one()
        user = appt_full.user

    await state.clear()

    # Notify client
    await send_reschedule_notice(call.bot, user, appt_full)

    # Reschedule reminder
    from scheduler.reminders import cancel_reminder, schedule_reminder

    cancel_reminder(appt_id)
    schedule_reminder(appt_full, user)

    await call.message.edit_text(
        f"✅ Запись *#{appt_id}* перенесена на *{data['reschedule_date']} {chosen_time} МСК*.\n"
        f"Клиент уведомлён.",
        parse_mode="Markdown",
    )
    await call.answer()


# ─── Admin cancel ─────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("admin_cancel:"))
async def admin_cancel_ask_reason(call: CallbackQuery, state: FSMContext) -> None:
    appt_id = int(call.data.split(":")[1])
    await state.set_state(AdminRescheduleFSM.WaitCancelReason)
    await state.update_data(cancel_appt_id=appt_id)
    await call.message.edit_text(
        f"❌ Отмена записи *#{appt_id}*\n\n"
        f"Введите причину отмены (или отправьте `-` чтобы пропустить):",
        parse_mode="Markdown",
    )
    await call.answer()


@router.message(AdminRescheduleFSM.WaitCancelReason)
async def admin_cancel_do(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    appt_id = data["cancel_appt_id"]
    reason = (
        message.text.strip() if message.text and message.text.strip() != "-" else ""
    )

    async with get_session() as session:
        try:
            await cancel_appointment_by_admin(session, appt_id, reason)
        except ValueError as e:
            await message.answer(str(e))
            return

        result = await session.execute(
            select(Appointment)
            .options(
                selectinload(Appointment.specialist),
                selectinload(Appointment.service),
                selectinload(Appointment.user),
            )
            .where(Appointment.id == appt_id)
        )
        appt_full = result.scalar_one()
        user = appt_full.user

    await state.clear()

    # Notify client
    await send_cancel_notice(message.bot, user, appt_full, reason)

    # Remove reminder
    from scheduler.reminders import cancel_reminder

    cancel_reminder(appt_id)

    await message.answer(
        f"✅ Запись *#{appt_id}* отменена. Клиент уведомлён.",
        parse_mode="Markdown",
    )
