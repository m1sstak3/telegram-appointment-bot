"""
Admin-role middleware.
Rejects /admin and admin callbacks for non-admin users.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from config import get_settings
from database import get_session
from models import User
from sqlalchemy import select


class AdminMiddleware(BaseMiddleware):
    """
    Applied only to the admin router.
    Checks that the incoming user has is_admin=True OR their telegram_id
    is in the ADMIN_IDS env list (auto-grants admin on first use).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        settings = get_settings()

        # Extract telegram_id
        if isinstance(event, Message):
            tg_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            tg_id = event.from_user.id if event.from_user else None
        else:
            tg_id = None

        if tg_id is None:
            return

        # Check DB or env list
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == tg_id)
            )
            user: User | None = result.scalar_one_or_none()

        is_admin = False
        if user and user.is_admin:
            is_admin = True
        elif tg_id in settings.admin_ids:
            # Auto-promote if listed in env
            if user:
                async with get_session() as session:
                    db_user = await session.get(User, user.id)
                    if db_user:
                        db_user.is_admin = True
            is_admin = True

        if not is_admin:
            if isinstance(event, Message):
                await event.answer(
                    "⛔ У вас нет доступа к панели администратора.\n"
                    "Если вы администратор — обратитесь к разработчику."
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Нет доступа.", show_alert=True)
            return

        return await handler(event, data)
