"""
Admin — Specialists CRUD.
Add, edit, toggle active status.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from database import get_session
from keyboards.admin import specialist_actions_keyboard, specialists_list_keyboard
from models import Specialist, SpecialistService, WorkSchedule
from sqlalchemy import select

router = Router()


class SpecialistFSM(StatesGroup):
    WaitName = State()
    WaitSpecialization = State()
    EditName = State()
    EditSpecialization = State()


# ─── List ──────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "admin:specialists")
async def list_specialists(call: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(Specialist).order_by(Specialist.name))
        specialists = result.scalars().all()
    await call.message.edit_text(
        "👨‍⚕️ *Специалисты*\n\nВыберите, чтобы управлять, или добавьте нового:",
        parse_mode="Markdown",
        reply_markup=specialists_list_keyboard(specialists),
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_sp:"))
async def specialist_detail(call: CallbackQuery) -> None:
    sp_id = int(call.data.split(":")[1])
    async with get_session() as session:
        sp = await session.get(Specialist, sp_id)
    if not sp:
        await call.answer("Специалист не найден.", show_alert=True)
        return
    status = "✅ Активен" if sp.is_active else "🔴 Деактивирован"
    await call.message.edit_text(
        f"👨‍⚕️ *{sp.name}*\n" f"🏥 {sp.specialization}\n" f"Статус: {status}",
        parse_mode="Markdown",
        reply_markup=specialist_actions_keyboard(sp.id, sp.is_active),
    )
    await call.answer()


# ─── Toggle active ─────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("admin_sp_toggle:"))
async def toggle_specialist(call: CallbackQuery) -> None:
    sp_id = int(call.data.split(":")[1])
    async with get_session() as session:
        sp = await session.get(Specialist, sp_id)
        if not sp:
            await call.answer("Не найден.", show_alert=True)
            return
        sp.is_active = not sp.is_active
    action = "активирован ✅" if sp.is_active else "деактивирован 🔴"
    await call.answer(f"Специалист {action}!", show_alert=False)
    await specialist_detail(call)


# ─── Add specialist ────────────────────────────────────────────────────────────


@router.callback_query(F.data == "admin_sp_add")
async def add_specialist_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SpecialistFSM.WaitName)
    await call.message.edit_text(
        "➕ *Добавить специалиста*\n\nВведите *ФИО* специалиста:",
        parse_mode="Markdown",
    )
    await call.answer()


@router.message(SpecialistFSM.WaitName)
async def add_specialist_name(message: Message, state: FSMContext) -> None:
    await state.update_data(sp_name=message.text.strip())
    await state.set_state(SpecialistFSM.WaitSpecialization)
    await message.answer(
        "🏥 Введите специализацию (например: *Терапевт*, *Хирург*, *Педиатр*):",
        parse_mode="Markdown",
    )


@router.message(SpecialistFSM.WaitSpecialization)
async def add_specialist_specialization(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    specialization = message.text.strip()

    async with get_session() as session:
        sp = Specialist(name=data["sp_name"], specialization=specialization)
        session.add(sp)
        await session.flush()

        # Default schedule: Mon–Fri 09:00–18:00, Sat–Sun off
        for weekday in range(5):
            session.add(
                WorkSchedule(
                    specialist_id=sp.id,
                    weekday=weekday,
                    start_time="09:00",
                    end_time="18:00",
                    is_day_off=False,
                )
            )
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

        # Link all active services
        from models import Service

        svc_result = await session.execute(
            select(Service).where(Service.is_active == True)
        )
        for svc in svc_result.scalars():
            session.add(SpecialistService(specialist_id=sp.id, service_id=svc.id))

    await state.clear()
    await message.answer(
        f"✅ Специалист *{data['sp_name']}* добавлен!\n"
        f"📅 Расписание по умолчанию: Пн–Пт 09:00–18:00. Скб/Вс — выходной.",
        parse_mode="Markdown",
    )
