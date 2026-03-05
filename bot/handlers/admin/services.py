"""
Admin — Services CRUD.
Add, edit, toggle active status.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from database import get_session
from keyboards.admin import service_actions_keyboard, services_list_keyboard
from models import Service
from sqlalchemy import select

router = Router()


class ServiceFSM(StatesGroup):
    WaitName = State()
    WaitDescription = State()
    WaitDuration = State()


# ─── List ──────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "admin:services")
async def list_services(call: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(Service).order_by(Service.name))
        services = result.scalars().all()
    await call.message.edit_text(
        "💼 *Услуги*\n\nВыберите услугу или добавьте новую:",
        parse_mode="Markdown",
        reply_markup=services_list_keyboard(services),
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_svc:"))
async def service_detail(call: CallbackQuery) -> None:
    svc_id = int(call.data.split(":")[1])
    async with get_session() as session:
        svc = await session.get(Service, svc_id)
    if not svc:
        await call.answer("Услуга не найдена.", show_alert=True)
        return
    status = "✅ Активна" if svc.is_active else "🔴 Деактивирована"
    await call.message.edit_text(
        f"💼 *{svc.name}*\n"
        f"📝 {svc.description or '—'}\n"
        f"⏱ Длительность: {svc.duration_min} мин.\n"
        f"Статус: {status}",
        parse_mode="Markdown",
        reply_markup=service_actions_keyboard(svc.id, svc.is_active),
    )
    await call.answer()


# ─── Toggle ────────────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("admin_svc_toggle:"))
async def toggle_service(call: CallbackQuery) -> None:
    svc_id = int(call.data.split(":")[1])
    async with get_session() as session:
        svc = await session.get(Service, svc_id)
        if not svc:
            await call.answer("Не найдена.", show_alert=True)
            return
        svc.is_active = not svc.is_active
    action = "активирована ✅" if svc.is_active else "деактивирована 🔴"
    await call.answer(f"Услуга {action}!", show_alert=False)
    await service_detail(call)


# ─── Add service ────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "admin_svc_add")
async def add_service_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ServiceFSM.WaitName)
    await call.message.edit_text(
        "➕ *Добавить услугу*\n\nВведите *название* услуги:\n\n"
        "Например: _Первичная консультация_",
        parse_mode="Markdown",
    )
    await call.answer()


@router.message(ServiceFSM.WaitName)
async def add_service_name(message: Message, state: FSMContext) -> None:
    await state.update_data(svc_name=message.text.strip())
    await state.set_state(ServiceFSM.WaitDescription)
    await message.answer("📝 Введите описание услуги (или `-` чтобы пропустить):")


@router.message(ServiceFSM.WaitDescription)
async def add_service_description(message: Message, state: FSMContext) -> None:
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(svc_desc=desc)
    await state.set_state(ServiceFSM.WaitDuration)
    await message.answer(
        "⏱ Введите длительность приёма в минутах (например: *30*, *60*, *90*):",
        parse_mode="Markdown",
    )


@router.message(ServiceFSM.WaitDuration)
async def add_service_duration(message: Message, state: FSMContext) -> None:
    try:
        duration = int(message.text.strip())
        if duration <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите целое положительное число (минуты).")
        return

    data = await state.get_data()
    async with get_session() as session:
        svc = Service(
            name=data["svc_name"], description=data["svc_desc"], duration_min=duration
        )
        session.add(svc)
        await session.flush()

        # Link all active specialists to this service
        from models import Specialist, SpecialistService

        sp_result = await session.execute(
            select(Specialist).where(Specialist.is_active == True)
        )
        for sp in sp_result.scalars():
            session.add(SpecialistService(specialist_id=sp.id, service_id=svc.id))

    await state.clear()
    await message.answer(
        f"✅ Услуга *{data['svc_name']}* ({duration} мин.) добавлена!\n"
        f"Все активные специалисты привязаны к этой услуге.",
        parse_mode="Markdown",
    )
