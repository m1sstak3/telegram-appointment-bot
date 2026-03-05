"""
/start handler and phone number collection.
Saves the user to DB on first visit, requests phone number.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Contact,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from database import get_session
from models import User
from sqlalchemy import select

router = Router()

_SHARE_PHONE_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if not user:
        return

    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user: User | None = result.scalar_one_or_none()

        if db_user is None:
            db_user = User(
                telegram_id=user.id,
                full_name=user.full_name or user.first_name or "Пользователь",
                username=user.username,
            )
            session.add(db_user)

    await state.clear()

    if db_user.phone:
        # Already registered — go straight to booking
        await message.answer(
            f"👋 С возвращением, *{db_user.full_name}*!\n\n"
            f"Нажмите кнопку ниже, чтобы записаться:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        await _show_start_menu(message)
    else:
        await message.answer(
            f"👋 Добро пожаловать, *{user.first_name}*!\n\n"
            f"Я помогу вам быстро записаться к специалисту прямо здесь, в Telegram.\n\n"
            f"Для начала, пожалуйста, поделитесь вашим *номером телефона* — "
            f"он нужен для подтверждения записи.",
            parse_mode="Markdown",
            reply_markup=_SHARE_PHONE_KB,
        )


@router.message(F.contact)
async def handle_contact(message: Message) -> None:
    contact: Contact = message.contact
    user = message.from_user
    if not user or not contact:
        return

    # Only accept the user's own contact (not someone else's shared card)
    if contact.user_id != user.id:
        await message.answer(
            "Пожалуйста, поделитесь *своим* номером телефона.", parse_mode="Markdown"
        )
        return

    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user: User | None = result.scalar_one_or_none()
        if db_user:
            db_user.phone = contact.phone_number
            db_user.full_name = (
                f"{contact.first_name} {contact.last_name or ''}".strip()
                or db_user.full_name
            )

    await message.answer(
        f"✅ Спасибо! Номер *{contact.phone_number}* сохранён.\n\n"
        f"Теперь вы можете записаться к специалисту:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _show_start_menu(message)


async def _show_start_menu(message: Message) -> None:
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Записаться к специалисту", callback_data="book:start")
    builder.button(text="🗓 Мои записи", callback_data="my_appts:list")
    builder.adjust(1)
    await message.answer(
        "Выберите действие:",
        reply_markup=builder.as_markup(),
    )
