"""Client-facing inline keyboards."""

from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build(builder: InlineKeyboardBuilder) -> InlineKeyboardMarkup:
    return builder.as_markup()


# ─── Service selection ────────────────────────────────────────────────────────


def services_keyboard(
    services: list, page: int = 0, per_page: int = 6
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    page_items = services[start : start + per_page]

    for svc in page_items:
        builder.button(text=f"💼 {svc.name}", callback_data=f"svc:{svc.id}")

    builder.adjust(1)

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"svc_page:{page - 1}")
        )
    if start + per_page < len(services):
        nav.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"svc_page:{page + 1}")
        )
    if nav:
        builder.row(*nav)

    return _build(builder)


# ─── Specialist selection ─────────────────────────────────────────────────────


def specialists_keyboard(
    specialists: list, service_id: int, page: int = 0, per_page: int = 6
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    page_items = specialists[start : start + per_page]

    for sp in page_items:
        builder.button(
            text=f"👨‍⚕️ {sp.name} — {sp.specialization}", callback_data=f"sp:{sp.id}"
        )

    builder.adjust(1)

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀️", callback_data=f"sp_page:{service_id}:{page - 1}"
            )
        )
    if start + per_page < len(specialists):
        nav.append(
            InlineKeyboardButton(
                text="▶️", callback_data=f"sp_page:{service_id}:{page + 1}"
            )
        )
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(text="⬅️ Назад к услугам", callback_data="back:services")
    )
    return _build(builder)


# ─── Calendar ─────────────────────────────────────────────────────────────────

_MONTH_RU = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}
_WEEK_HEADER = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def calendar_keyboard(
    available_dates: set[date],
    today: date,
    horizon_days: int = 30,
    offset_weeks: int = 0,
) -> InlineKeyboardMarkup:
    """Render a calendar showing weeks for the booking horizon."""
    builder = InlineKeyboardBuilder()

    # Header row — weekday names
    header = [
        InlineKeyboardButton(text=d, callback_data="ignore") for d in _WEEK_HEADER
    ]
    builder.row(*header)

    # Build weeks
    start_of_range = today + timedelta(days=offset_weeks * 7)
    end_of_range = today + timedelta(days=horizon_days)

    # Start from Monday of the current week (relative to offset)
    week_start = start_of_range - timedelta(days=start_of_range.weekday())

    weeks_shown = 0
    current = week_start
    while current <= end_of_range and weeks_shown < 5:
        week_buttons = []
        for i in range(7):
            d = current + timedelta(days=i)
            if d < today or d > end_of_range:
                week_buttons.append(
                    InlineKeyboardButton(text=" ", callback_data="ignore")
                )
            elif d in available_dates:
                week_buttons.append(
                    InlineKeyboardButton(
                        text=f"✅ {d.day}", callback_data=f"date:{d.isoformat()}"
                    )
                )
            else:
                week_buttons.append(
                    InlineKeyboardButton(text=f"{d.day}", callback_data="ignore")
                )
        builder.row(*week_buttons)
        current += timedelta(days=7)
        weeks_shown += 1

    # Navigation
    nav = []
    if offset_weeks > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀️ Пред. неделя", callback_data=f"cal_week:{offset_weeks - 1}"
            )
        )
    max_weeks = (horizon_days // 7) + 1
    if offset_weeks < max_weeks - 1:
        nav.append(
            InlineKeyboardButton(
                text="След. неделя ▶️", callback_data=f"cal_week:{offset_weeks + 1}"
            )
        )
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к специалисту", callback_data="back:specialists"
        )
    )
    return _build(builder)


# ─── Time slot selection ──────────────────────────────────────────────────────


def timeslots_keyboard(slots: list[str], chosen_date: str) -> InlineKeyboardMarkup:
    """slots: list of 'HH:MM' strings (local Moscow time)."""
    builder = InlineKeyboardBuilder()
    for t in slots:
        builder.button(text=f"🕐 {t}", callback_data=f"time:{t}")
    builder.adjust(3)
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад к календарю", callback_data="back:calendar")
    )
    return _build(builder)


# ─── Booking confirmation ─────────────────────────────────────────────────────


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, всё верно", callback_data="confirm:yes")
    builder.button(text="✏️ Нет, изменить данные", callback_data="confirm:edit")
    builder.button(text="❌ Отменить запись", callback_data="confirm:cancel")
    builder.adjust(1)
    return _build(builder)


def edit_booking_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💼 Изменить услугу", callback_data="back:services")
    builder.button(text="👨‍⚕️ Изменить специалиста", callback_data="back:specialists")
    builder.button(text="📅 Изменить дату", callback_data="back:calendar")
    builder.button(text="🕐 Изменить время", callback_data="back:time")
    builder.button(text="❌ Отменить совсем", callback_data="confirm:cancel")
    builder.adjust(1)
    return _build(builder)


# ─── My appointments ──────────────────────────────────────────────────────────


def my_appointments_keyboard(appointments: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for appt in appointments:
        builder.button(
            text=f"❌ Отменить #{appt.id}",
            callback_data=f"cancel_appt:{appt.id}",
        )
    builder.adjust(1)
    return _build(builder)


def cancel_confirm_keyboard(appt_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, отменить", callback_data=f"cancel_confirm:{appt_id}")
    builder.button(text="◀️ Нет, вернуться", callback_data="cancel_abort")
    builder.adjust(1)
    return _build(builder)
