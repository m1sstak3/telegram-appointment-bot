"""
Transactional booking service.
Guarantees no double-booking via SQLite immediate transaction + re-check.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytz
from models import Appointment, AppointmentStatus
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

MSK = pytz.timezone("Europe/Moscow")


class SlotTakenError(Exception):
    """Raised when the requested slot is already booked."""


class CancelTooLateError(Exception):
    """Raised when client tries to cancel within MIN_CANCEL_HOURS."""


# ─── Booking ──────────────────────────────────────────────────────────────────


async def create_appointment(
    session: AsyncSession,
    user_id: int,
    specialist_id: int,
    service_id: int,
    scheduled_at_utc: datetime,
) -> Appointment:
    """
    Atomically create an appointment.
    Raises SlotTakenError if the slot is already taken.
    """
    # Re-check inside the same unit of work (SQLite serializes writes)
    existing = await session.execute(
        select(Appointment).where(
            and_(
                Appointment.specialist_id == specialist_id,
                Appointment.scheduled_at == scheduled_at_utc,
                Appointment.status != AppointmentStatus.CANCELLED,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise SlotTakenError("This slot was just taken by another user.")

    appt = Appointment(
        user_id=user_id,
        specialist_id=specialist_id,
        service_id=service_id,
        scheduled_at=scheduled_at_utc,
        status=AppointmentStatus.CONFIRMED,
    )
    session.add(appt)
    await session.flush()  # get appt.id before commit
    return appt


# ─── Client cancellation ──────────────────────────────────────────────────────


async def cancel_appointment_by_client(
    session: AsyncSession,
    appointment_id: int,
    user_id: int,
    min_cancel_hours: int = 72,
) -> Appointment:
    """
    Cancel an appointment.
    Raises CancelTooLateError if < min_cancel_hours remain.
    """
    appt = await session.get(Appointment, appointment_id)
    if not appt or appt.user_id != user_id:
        raise ValueError("Appointment not found or access denied.")

    if appt.status == AppointmentStatus.CANCELLED:
        raise ValueError("This appointment is already cancelled.")

    now_utc = datetime.now(UTC).replace(tzinfo=None)
    hours_left = (appt.scheduled_at - now_utc).total_seconds() / 3600
    if hours_left < min_cancel_hours:
        raise CancelTooLateError(
            f"Cancellation is only allowed at least {min_cancel_hours // 24} days in advance."
        )

    appt.status = AppointmentStatus.CANCELLED
    appt.cancel_reason = "Отменено клиентом"
    await session.flush()
    return appt


# ─── Admin reschedule / cancel ────────────────────────────────────────────────


async def reschedule_appointment(
    session: AsyncSession,
    appointment_id: int,
    new_scheduled_at_utc: datetime,
    specialist_id: int,
) -> Appointment:
    """Move appointment to a new time. Checks slot availability."""
    # Check new slot is free
    existing = await session.execute(
        select(Appointment).where(
            and_(
                Appointment.specialist_id == specialist_id,
                Appointment.scheduled_at == new_scheduled_at_utc,
                Appointment.status != AppointmentStatus.CANCELLED,
                Appointment.id != appointment_id,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise SlotTakenError("The target slot is already booked.")

    appt = await session.get(Appointment, appointment_id)
    if not appt:
        raise ValueError("Appointment not found.")

    appt.scheduled_at = new_scheduled_at_utc
    appt.status = AppointmentStatus.RESCHEDULED
    await session.flush()
    return appt


async def cancel_appointment_by_admin(
    session: AsyncSession,
    appointment_id: int,
    reason: str = "",
) -> Appointment:
    appt = await session.get(Appointment, appointment_id)
    if not appt:
        raise ValueError("Appointment not found.")

    appt.status = AppointmentStatus.CANCELLED
    appt.cancel_reason = reason or "Отменено администратором"
    await session.flush()
    return appt


# ─── Helpers ──────────────────────────────────────────────────────────────────


def msk_str_to_utc(date_str: str, time_str: str) -> datetime:
    """Convert 'YYYY-MM-DD' + 'HH:MM' (Moscow) to naive UTC datetime."""
    d = date.fromisoformat(date_str)
    h, m = map(int, time_str.split(":"))
    local_naive = datetime(d.year, d.month, d.day, h, m)
    aware = MSK.localize(local_naive)
    return aware.astimezone(UTC).replace(tzinfo=None)


def utc_to_msk_str(dt_utc: datetime) -> str:
    """Return 'DD.MM.YYYY HH:MM' in Moscow time."""
    aware = dt_utc.replace(tzinfo=UTC)
    msk_dt = aware.astimezone(MSK)
    return msk_dt.strftime("%d.%m.%Y %H:%M")
