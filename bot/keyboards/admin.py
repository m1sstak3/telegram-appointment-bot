"""Admin-facing inline keyboards."""

from __future__ import annotations

from datetime import UTC

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from models import Appointment, Service, Specialist


def _build(builder: InlineKeyboardBuilder) -> InlineKeyboardMarkup:
    return builder.as_markup()


# ─── Admin main menu ──────────────────────────────────────────────────────────


def admin_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Записи", callback_data="admin:appointments")
    builder.button(text="👨‍⚕️ Специалисты", callback_data="admin:specialists")
    builder.button(text="💼 Услуги", callback_data="admin:services")
    builder.adjust(1)
    return _build(builder)


# ─── Appointments list ────────────────────────────────────────────────────────


def appointments_filter_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Все записи", callback_data="appt_filter:all")
    builder.button(text="🔜 Предстоящие", callback_data="appt_filter:upcoming")
    builder.button(text="✅ Завершённые", callback_data="appt_filter:confirmed")
    builder.button(text="❌ Отменённые", callback_data="appt_filter:cancelled")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="admin:menu"))
    return _build(builder)


def appointment_actions_keyboard(appt_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Перенести", callback_data=f"admin_reschedule:{appt_id}")
    builder.button(text="❌ Отменить", callback_data=f"admin_cancel:{appt_id}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="appt_filter:all")
    )
    return _build(builder)


def appointments_list_keyboard(
    appointments: list[Appointment], page: int = 0, per_page: int = 5
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    page_items = appointments[start : start + per_page]

    for appt in page_items:
        # Import here to avoid circular

        import pytz

        tz = pytz.timezone("Europe/Moscow")
        local_dt = appt.scheduled_at.replace(tzinfo=UTC).astimezone(tz)
        label = f"#{appt.id} {local_dt.strftime('%d.%m %H:%M')} — {appt.specialist.name[:15]}"
        builder.button(text=label, callback_data=f"admin_appt:{appt.id}")

    builder.adjust(1)

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀️", callback_data=f"appt_page:{page - 1}")
        )
    if start + per_page < len(appointments):
        nav.append(
            InlineKeyboardButton(text="▶️", callback_data=f"appt_page:{page + 1}")
        )
    if nav:
        builder.row(*nav)

    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="admin:menu"))
    return _build(builder)


def reschedule_date_select_keyboard(
    available_dates: set, specialist_id: int
) -> InlineKeyboardMarkup:
    """Simple list of available dates for rescheduling."""
    builder = InlineKeyboardBuilder()
    sorted_dates = sorted(available_dates)
    for d in sorted_dates[:10]:  # show max 10 dates
        builder.button(
            text=d.strftime("%d.%m.%Y (%a)"),
            callback_data=f"reschedule_date:{d.isoformat()}",
        )
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Отмена", callback_data="appt_filter:all"))
    return _build(builder)


def reschedule_time_select_keyboard(
    slots: list[str], appt_id: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in slots:
        builder.button(text=f"🕐 {t}", callback_data=f"reschedule_time:{t}")
    builder.adjust(3)
    builder.row(
        InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_appt:{appt_id}")
    )
    return _build(builder)


# ─── Specialists CRUD ─────────────────────────────────────────────────────────


def specialists_list_keyboard(specialists: list[Specialist]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sp in specialists:
        status = "✅" if sp.is_active else "🔴"
        builder.button(text=f"{status} {sp.name}", callback_data=f"admin_sp:{sp.id}")
    builder.adjust(1)
    builder.button(text="➕ Добавить специалиста", callback_data="admin_sp_add")
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="admin:menu"))
    return _build(builder)


def specialist_actions_keyboard(sp_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать", callback_data=f"admin_sp_edit:{sp_id}")
    toggle_text = "🔴 Деактивировать" if is_active else "✅ Активировать"
    builder.button(text=toggle_text, callback_data=f"admin_sp_toggle:{sp_id}")
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:specialists")
    )
    return _build(builder)


# ─── Services CRUD ────────────────────────────────────────────────────────────


def services_list_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for svc in services:
        status = "✅" if svc.is_active else "🔴"
        builder.button(text=f"{status} {svc.name}", callback_data=f"admin_svc:{svc.id}")
    builder.adjust(1)
    builder.button(text="➕ Добавить услугу", callback_data="admin_svc_add")
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="admin:menu"))
    return _build(builder)


def service_actions_keyboard(svc_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать", callback_data=f"admin_svc_edit:{svc_id}")
    toggle_text = "🔴 Деактивировать" if is_active else "✅ Активировать"
    builder.button(text=toggle_text, callback_data=f"admin_svc_toggle:{svc_id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:services"))
    return _build(builder)


def back_to_admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В главное меню", callback_data="admin:menu")
    return _build(builder)
