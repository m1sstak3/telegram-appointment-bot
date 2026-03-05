"""
Admin panel — main menu entry via /admin command.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from keyboards.admin import admin_main_menu

router = Router()


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer(
        "🔐 *Панель администратора*\n\nВыберите раздел:",
        parse_mode="Markdown",
        reply_markup=admin_main_menu(),
    )


@router.callback_query(F.data == "admin:menu")
async def admin_menu_cb(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "🔐 *Панель администратора*\n\nВыберите раздел:",
        parse_mode="Markdown",
        reply_markup=admin_main_menu(),
    )
    await call.answer()
