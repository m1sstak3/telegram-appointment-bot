"""
Booking FSM handler.

Flow:
  book:start
    → SelectService   (show services)
    → SelectSpecialist (filtered by service)
    → SelectDate      (calendar with available dates)
    → SelectTime      (time slots for chosen date)
    → ConfirmBooking  (summary + confirm button)
    → [booking created] → confirmation message
"""

from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery
from config import get_settings
from database import get_session
from keyboards.client import (
    calendar_keyboard,
    confirm_keyboard,
    edit_booking_keyboard,
    services_keyboard,
    specialists_keyboard,
    timeslots_keyboard,
)
from models import Appointment, Service, Specialist, SpecialistService, User
from services.booking_service import SlotTakenError, create_appointment, msk_str_to_utc
from services.notification_service import send_booking_confirmation
from services.slot_service import get_available_dates, get_free_slots_for_date
from sqlalchemy import select

router = Router()
settings = get_settings()


# ─── States ───────────────────────────────────────────────────────────────────


class BookingFSM(StatesGroup):
    SelectService = State()
    SelectSpecialist = State()
    SelectDate = State()
    SelectTime = State()
    ConfirmBooking = State()


# ─── Entry point ──────────────────────────────────────────────────────────────


@router.callback_query(F.data == "book:start")
async def booking_start(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    async with get_session() as session:
        result = await session.execute(
            select(Service).where(Service.is_active == True).order_by(Service.name)
        )
        services = result.scalars().all()

    if not services:
        await call.message.edit_text("😔 Услуги временно недоступны. Попробуйте позже.")
        return

    await state.set_state(BookingFSM.SelectService)
    await state.update_data(svc_page=0)
    await call.message.edit_text(
        "💼 *Шаг 1 из 4: Выберите услугу*",
        parse_mode="Markdown",
        reply_markup=services_keyboard(services, page=0),
    )


# ─── Service selection ────────────────────────────────────────────────────────


@router.callback_query(BookingFSM.SelectService, F.data.startswith("svc:"))
async def select_service(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    service_id = int(call.data.split(":")[1])
    async with get_session() as session:
        service = await session.get(Service, service_id)
        if not service:
            await call.answer("Услуга не найдена.", show_alert=True)
            return
        # Load specialists for this service
        result = await session.execute(
            select(Specialist)
            .join(SpecialistService, SpecialistService.specialist_id == Specialist.id)
            .where(
                SpecialistService.service_id == service_id,
                Specialist.is_active == True,
            )
            .order_by(Specialist.name)
        )
        specialists = result.scalars().all()

    if not specialists:
        await call.answer("Нет доступных специалистов по этой услуге.", show_alert=True)
        return

    await state.update_data(service_id=service_id, service_name=service.name, sp_page=0)
    await state.set_state(BookingFSM.SelectSpecialist)
    await call.message.edit_text(
        f"💼 Услуга: *{service.name}*\n\n" f"👨‍⚕️ *Шаг 2 из 4: Выберите специалиста*",
        parse_mode="Markdown",
        reply_markup=specialists_keyboard(specialists, service_id, page=0),
    )


@router.callback_query(BookingFSM.SelectService, F.data.startswith("svc_page:"))
async def paginate_services(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    page = int(call.data.split(":")[1])
    async with get_session() as session:
        result = await session.execute(
            select(Service).where(Service.is_active == True).order_by(Service.name)
        )
        services = result.scalars().all()

    await call.message.edit_reply_markup(
        reply_markup=services_keyboard(services, page=page)
    )


# ─── Specialist selection ─────────────────────────────────────────────────────


@router.callback_query(BookingFSM.SelectSpecialist, F.data.startswith("sp:"))
async def select_specialist(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    specialist_id = int(call.data.split(":")[1])
    data = await state.get_data()
    service_id = data["service_id"]
    service_name = data["service_name"]

    async with get_session() as session:
        sp = await session.get(Specialist, specialist_id)
        if not sp:
            await call.answer("Специалист не найден.", show_alert=True)
            return
        available_dates = await get_available_dates(
            session, specialist_id, service_id, settings.booking_horizon_days
        )

    if not available_dates:
        await call.answer(
            "😔 Нет свободных слотов у этого специалиста в ближайшие 30 дней.",
            show_alert=True,
        )
        return

    await state.update_data(
        specialist_id=specialist_id,
        specialist_name=f"{sp.name} ({sp.specialization})",
        available_dates=[d.isoformat() for d in available_dates],
        cal_offset=0,
    )
    await state.set_state(BookingFSM.SelectDate)
    today = date.today()
    await call.message.edit_text(
        f"💼 {service_name}\n"
        f"👨‍⚕️ *{sp.name}*\n\n"
        f"📅 *Шаг 3 из 4: Выберите дату*\n\n"
        f"✅ — доступные дни",
        parse_mode="Markdown",
        reply_markup=calendar_keyboard(
            available_dates, today, settings.booking_horizon_days, offset_weeks=0
        ),
    )


@router.callback_query(BookingFSM.SelectSpecialist, F.data.startswith("sp_page:"))
async def paginate_specialists(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    _, service_id_str, page_str = call.data.split(":")
    service_id, page = int(service_id_str), int(page_str)
    async with get_session() as session:
        result = await session.execute(
            select(Specialist)
            .join(SpecialistService, SpecialistService.specialist_id == Specialist.id)
            .where(
                SpecialistService.service_id == service_id, Specialist.is_active == True
            )
            .order_by(Specialist.name)
        )
        specialists = result.scalars().all()
    await call.message.edit_reply_markup(
        reply_markup=specialists_keyboard(specialists, service_id, page=page)
    )


# ─── Calendar navigation ──────────────────────────────────────────────────────


@router.callback_query(BookingFSM.SelectDate, F.data.startswith("cal_week:"))
async def calendar_navigate(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    offset = int(call.data.split(":")[1])
    data = await state.get_data()
    available_dates = {date.fromisoformat(d) for d in data["available_dates"]}
    await state.update_data(cal_offset=offset)
    await call.message.edit_reply_markup(
        reply_markup=calendar_keyboard(
            available_dates,
            date.today(),
            settings.booking_horizon_days,
            offset_weeks=offset,
        )
    )


@router.callback_query(BookingFSM.SelectDate, F.data.startswith("date:"))
async def select_date(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    chosen_date_str = call.data.split(":")[1]
    data = await state.get_data()

    async with get_session() as session:
        slots = await get_free_slots_for_date(
            session,
            data["specialist_id"],
            data["service_id"],
            date.fromisoformat(chosen_date_str),
        )

    if not slots:
        await call.answer("Нет свободных слотов на эту дату.", show_alert=True)
        return

    await state.update_data(chosen_date=chosen_date_str)
    await state.set_state(BookingFSM.SelectTime)
    await call.message.edit_text(
        f"📅 Дата: *{date.fromisoformat(chosen_date_str).strftime('%d.%m.%Y')}*\n\n"
        f"🕐 *Шаг 4 из 4: Выберите время (МСК)*",
        parse_mode="Markdown",
        reply_markup=timeslots_keyboard(slots, chosen_date_str),
    )


# ─── Time selection → confirmation ───────────────────────────────────────────


@router.callback_query(BookingFSM.SelectTime, F.data.startswith("time:"))
async def select_time(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    chosen_time = call.data.split(":", 1)[1]
    data = await state.get_data()

    await state.update_data(chosen_time=chosen_time)
    await state.set_state(BookingFSM.ConfirmBooking)

    summary = (
        f"📋 *Проверьте данные записи:*\n\n"
        f"💼 Услуга: *{data['service_name']}*\n"
        f"👨‍⚕️ Специалист: *{data['specialist_name']}*\n"
        f"📅 Дата: *{date.fromisoformat(data['chosen_date']).strftime('%d.%m.%Y')}*\n"
        f"🕐 Время: *{chosen_time} МСК*\n\n"
        f"Всё верно?"
    )
    await call.message.edit_text(
        summary, parse_mode="Markdown", reply_markup=confirm_keyboard()
    )


# ─── Confirm / cancel booking ─────────────────────────────────────────────────


@router.callback_query(BookingFSM.ConfirmBooking, F.data == "confirm:yes")
async def confirm_booking(call: CallbackQuery, state: FSMContext) -> None:
    # Disable buttons immediately to prevent double-clicks
    await call.message.edit_reply_markup(reply_markup=None)

    data = await state.get_data()
    tg_id = call.from_user.id

    async with get_session() as session:
        # Load user record
        from sqlalchemy import select as sa_select

        result = await session.execute(sa_select(User).where(User.telegram_id == tg_id))
        db_user: User | None = result.scalar_one_or_none()
        if not db_user:
            await call.answer("Пожалуйста, начните с /start", show_alert=True)
            return

        await call.answer("Оформляем запись...", show_alert=False)

        scheduled_utc = msk_str_to_utc(data["chosen_date"], data["chosen_time"])

        try:
            appt = await create_appointment(
                session,
                user_id=db_user.id,
                specialist_id=data["specialist_id"],
                service_id=data["service_id"],
                scheduled_at_utc=scheduled_utc,
            )
        except SlotTakenError:
            await call.message.edit_text(
                "😔 К сожалению, этот слот только что был занят другим пользователем.\n"
                "Пожалуйста, выберите другое время.",
                reply_markup=None,
            )
            await state.clear()
            return

        # Load relationships for notification
        from sqlalchemy.orm import selectinload

        appt_loaded = await session.execute(
            sa_select(Appointment)
            .options(
                selectinload(Appointment.specialist),
                selectinload(Appointment.service),
                selectinload(Appointment.user),
            )
            .where(Appointment.id == appt.id)
        )
        appt_full = appt_loaded.scalar_one()

    await state.clear()
    await call.message.edit_text(
        f"✅ *Запись создана!*\n\n"
        f"💼 {data['service_name']}\n"
        f"👨‍⚕️ {data['specialist_name']}\n"
        f"📅 {date.fromisoformat(data['chosen_date']).strftime('%d.%m.%Y')} в {data['chosen_time']} МСК\n\n"
        f"Детали также отправлены вам в сообщении ниже.",
        parse_mode="Markdown",
    )

    # Send confirmation notice
    await send_booking_confirmation(call.bot, db_user, appt_full)

    # Schedule 24h reminder
    from scheduler.reminders import schedule_reminder

    schedule_reminder(appt_full, db_user)


@router.callback_query(BookingFSM.ConfirmBooking, F.data == "confirm:edit")
async def edit_booking(call: CallbackQuery, state: FSMContext) -> None:
    await call.message.edit_text(
        "✏️ Что именно вы хотите изменить?", reply_markup=edit_booking_keyboard()
    )


@router.callback_query(BookingFSM.ConfirmBooking, F.data == "confirm:cancel")
async def cancel_booking(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("❌ Запись отменена. Для новой записи нажмите /start")


# ─── Back navigation ──────────────────────────────────────────────────────────


@router.callback_query(F.data == "back:services")
async def back_to_services(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(BookingFSM.SelectService)
    async with get_session() as session:
        result = await session.execute(
            select(Service).where(Service.is_active == True).order_by(Service.name)
        )
        services = result.scalars().all()
    await call.message.edit_text(
        "💼 *Шаг 1 из 4: Выберите услугу*",
        parse_mode="Markdown",
        reply_markup=services_keyboard(services),
    )


@router.callback_query(F.data == "back:specialists")
async def back_to_specialists(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    data = await state.get_data()
    service_id = data.get("service_id")
    if not service_id:
        await back_to_services(call, state)
        return

    await state.set_state(BookingFSM.SelectSpecialist)
    async with get_session() as session:
        result = await session.execute(
            select(Specialist)
            .join(SpecialistService, SpecialistService.specialist_id == Specialist.id)
            .where(
                SpecialistService.service_id == service_id, Specialist.is_active == True
            )
            .order_by(Specialist.name)
        )
        specialists = result.scalars().all()
    await call.message.edit_text(
        f"💼 {data.get('service_name', '')}\n\n"
        f"👨‍⚕️ *Шаг 2 из 4: Выберите специалиста*",
        parse_mode="Markdown",
        reply_markup=specialists_keyboard(specialists, service_id),
    )


@router.callback_query(F.data == "back:calendar")
async def back_to_calendar(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    data = await state.get_data()
    if not data.get("specialist_id"):
        await back_to_specialists(call, state)
        return

    async with get_session() as session:
        available_dates = await get_available_dates(
            session,
            data["specialist_id"],
            data["service_id"],
            settings.booking_horizon_days,
        )

    await state.set_state(BookingFSM.SelectDate)
    await call.message.edit_text(
        "📅 *Шаг 3 из 4: Выберите дату*",
        parse_mode="Markdown",
        reply_markup=calendar_keyboard(
            available_dates, date.today(), settings.booking_horizon_days, offset_weeks=0
        ),
    )


@router.callback_query(F.data == "back:time")
async def back_to_time(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    data = await state.get_data()
    if not data.get("chosen_date"):
        await back_to_calendar(call, state)
        return

    async with get_session() as session:
        slots = await get_free_slots_for_date(
            session,
            data["specialist_id"],
            data["service_id"],
            date.fromisoformat(data["chosen_date"]),
        )

    await state.set_state(BookingFSM.SelectTime)
    await call.message.edit_text(
        f"📅 Дата: *{date.fromisoformat(data['chosen_date']).strftime('%d.%m.%Y')}*\n\n"
        f"🕐 *Шаг 4 из 4: Выберите время (МСК)*",
        parse_mode="Markdown",
        reply_markup=timeslots_keyboard(slots, data["chosen_date"]),
    )


@router.callback_query(F.data == "ignore")
async def noop(call: CallbackQuery) -> None:
    await call.answer()
