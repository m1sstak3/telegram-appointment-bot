"""
Slot availability service.

Generates available time slots for a specialist on a given date,
taking into account:
  - their WorkSchedule (working hours, days off)
  - already-booked Appointments (excluding cancelled)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytz
from models import Appointment, AppointmentStatus, Service, Specialist, WorkSchedule
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

MSK = pytz.timezone("Europe/Moscow")


def _msk_now() -> datetime:
    return datetime.now(tz=MSK)


def _utc_from_msk(dt_msk: datetime) -> datetime:
    """Convert naive Moscow datetime to UTC datetime (naive)."""
    aware = MSK.localize(dt_msk)
    return aware.astimezone(UTC).replace(tzinfo=None)


def _msk_from_utc(dt_utc: datetime) -> datetime:
    """Convert naive UTC datetime to Moscow datetime (naive)."""
    aware = dt_utc.replace(tzinfo=UTC)
    return aware.astimezone(MSK).replace(tzinfo=None)


# ─── Public API ───────────────────────────────────────────────────────────────


async def get_available_dates(
    session: AsyncSession,
    specialist_id: int,
    service_id: int,
    horizon_days: int = 30,
) -> set[date]:
    """Return the set of dates that have at least one free slot."""
    specialist = await _load_specialist(session, specialist_id)
    if not specialist:
        return set()

    service = await session.get(Service, service_id)
    if not service:
        return set()

    today_msk = _msk_now().date()
    window_start_utc = _utc_from_msk(
        datetime(today_msk.year, today_msk.month, today_msk.day, 0, 0)
    )
    window_end_msk = today_msk + timedelta(days=horizon_days)
    window_end_utc = _utc_from_msk(
        datetime(
            window_end_msk.year, window_end_msk.month, window_end_msk.day, 23, 59, 59
        )
    )

    # Fetch ALL booked slots for the next 30 days in ONE query
    result = await session.execute(
        select(Appointment.scheduled_at).where(
            and_(
                Appointment.specialist_id == specialist.id,
                Appointment.scheduled_at >= window_start_utc,
                Appointment.scheduled_at <= window_end_utc,
                Appointment.status != AppointmentStatus.CANCELLED,
            )
        )
    )
    all_booked_utc: set[datetime] = {row[0] for row in result.fetchall()}
    all_booked_msk: set[datetime] = {_msk_from_utc(dt) for dt in all_booked_utc}

    available: set[date] = set()
    for delta in range(horizon_days):
        d = today_msk + timedelta(days=delta)
        slots = _calc_free_slots_in_memory(specialist, service, d, all_booked_msk)
        if slots:
            available.add(d)

    return available


async def get_free_slots_for_date(
    session: AsyncSession,
    specialist_id: int,
    service_id: int,
    chosen_date: date,
) -> list[str]:
    """Return list of free slot strings 'HH:MM' (Moscow time) for a given date."""
    specialist = await _load_specialist(session, specialist_id)
    if not specialist:
        return []
    service = await session.get(Service, service_id)
    if not service:
        return []

    day_start_utc = _utc_from_msk(
        datetime(chosen_date.year, chosen_date.month, chosen_date.day, 0, 0)
    )
    day_end_utc = _utc_from_msk(
        datetime(chosen_date.year, chosen_date.month, chosen_date.day, 23, 59, 59)
    )

    result = await session.execute(
        select(Appointment.scheduled_at).where(
            and_(
                Appointment.specialist_id == specialist.id,
                Appointment.scheduled_at >= day_start_utc,
                Appointment.scheduled_at <= day_end_utc,
                Appointment.status != AppointmentStatus.CANCELLED,
            )
        )
    )
    booked_utc: set[datetime] = {row[0] for row in result.fetchall()}
    booked_msk: set[datetime] = {_msk_from_utc(dt) for dt in booked_utc}

    slots = _calc_free_slots_in_memory(specialist, service, chosen_date, booked_msk)
    return [t.strftime("%H:%M") for t in slots]


# ─── Internal ─────────────────────────────────────────────────────────────────


async def _load_specialist(
    session: AsyncSession, specialist_id: int
) -> Specialist | None:
    result = await session.execute(
        select(Specialist)
        .options(selectinload(Specialist.schedules))
        .where(Specialist.id == specialist_id, Specialist.is_active == True)
    )
    return result.scalar_one_or_none()


def _calc_free_slots_in_memory(
    specialist: Specialist,
    service: Service,
    d: date,
    booked_msk: set[datetime],
) -> list[time]:
    """Generate and return free time slots (Moscow time objects) for a date from pre-fetched data."""
    weekday = d.weekday()  # 0=Mon

    # Find schedule for this weekday
    schedule: WorkSchedule | None = next(
        (s for s in specialist.schedules if s.weekday == weekday), None
    )
    if not schedule or schedule.is_day_off:
        return []

    # Parse working hours
    start_h, start_m = map(int, schedule.start_time.split(":"))
    end_h, end_m = map(int, schedule.end_time.split(":"))

    slot_duration = timedelta(minutes=service.duration_min)
    current = datetime(d.year, d.month, d.day, start_h, start_m)
    end_dt = datetime(d.year, d.month, d.day, end_h, end_m)

    # Build candidate slots (naive Moscow datetimes)
    candidates: list[datetime] = []
    while current + slot_duration <= end_dt:
        candidates.append(current)
        current += slot_duration

    if not candidates:
        return []

    # Now in Moscow — filter out past slots
    now_msk = _msk_now().replace(tzinfo=None)
    candidates = [c for c in candidates if c > now_msk]

    free = [c for c in candidates if c not in booked_msk]
    return [c.time() for c in free]
