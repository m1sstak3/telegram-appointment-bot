"""
Database initialization script.
Creates all tables and seeds demo data.

Usage:
    python init_db.py
"""

from __future__ import annotations

import asyncio
import os

from database import engine
from models import Base, Service, Specialist, SpecialistService, WorkSchedule
from sqlalchemy import text

# ─── Seed data ────────────────────────────────────────────────────────────────

SERVICES = [
    {
        "name": "Первичная консультация",
        "description": "Первичный осмотр и консультация врача.",
        "duration_min": 60,
    },
    {
        "name": "Повторная консультация",
        "description": "Повторный приём по ранее назначенному лечению.",
        "duration_min": 30,
    },
    {
        "name": "Диагностика",
        "description": "Комплексное диагностическое обследование.",
        "duration_min": 90,
    },
    {
        "name": "Процедура",
        "description": "Лечебная процедура или инъекция.",
        "duration_min": 30,
    },
]

SPECIALISTS = [
    {"name": "Иванова Мария Петровна", "specialization": "Терапевт"},
    {"name": "Смирнов Алексей Дмитриевич", "specialization": "Хирург"},
    {"name": "Кузнецова Ольга Игоревна", "specialization": "Педиатр"},
]

# Monday..Friday = 0..4; Saturday=5, Sunday=6
WEEKDAYS_MON_FRI = list(range(5))  # 0-4

WORK_HOURS = {"start_time": "09:00", "end_time": "18:00"}


async def seed():
    from database import async_session_factory

    async with async_session_factory() as session:
        # Check if already seeded
        result = await session.execute(text("SELECT COUNT(*) FROM services"))
        count = result.scalar()
        if count > 0:
            print("DB already seeded — skipping.")
            return

        # Services
        service_objs: list[Service] = []
        for s in SERVICES:
            obj = Service(**s)
            session.add(obj)
            service_objs.append(obj)

        await session.flush()  # get IDs

        # Specialists + their work schedules
        for sp_data in SPECIALISTS:
            sp = Specialist(**sp_data)
            session.add(sp)
            await session.flush()

            for weekday in WEEKDAYS_MON_FRI:
                schedule = WorkSchedule(
                    specialist_id=sp.id,
                    weekday=weekday,
                    **WORK_HOURS,
                    is_day_off=False,
                )
                session.add(schedule)

            # Saturday — day off
            for weekend in [5, 6]:
                session.add(
                    WorkSchedule(
                        specialist_id=sp.id,
                        weekday=weekend,
                        start_time="09:00",
                        end_time="18:00",
                        is_day_off=True,
                    )
                )

            # Link all services to all specialists for demo
            for svc in service_objs:
                session.add(SpecialistService(specialist_id=sp.id, service_id=svc.id))

        await session.commit()
        print("[OK] Database seeded with demo data.")


async def main():
    os.makedirs("data", exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] Tables created.")

    await seed()


if __name__ == "__main__":
    asyncio.run(main())
