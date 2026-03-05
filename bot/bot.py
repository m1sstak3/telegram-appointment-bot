"""
Bot entry point.
Initialises dispatcher, registers all routers, starts APScheduler, runs polling.
"""

from __future__ import annotations

import asyncio
import logging

import sentry_sdk
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from config import get_settings
from database import engine
from models import Base

# ─── Settings ─────────────────────────────────────────────────────────────────
settings = get_settings()

# ─── Sentry ───────────────────────────────────────────────────────────────────
if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.2)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    import os

    os.makedirs("data", exist_ok=True)

    # Create tables if not exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # ── Register client routers ──────────────────────────────────────────────────
    from handlers.booking import router as booking_router
    from handlers.my_appointments import router as my_appts_router
    from handlers.start import router as start_router

    dp.include_router(start_router)
    dp.include_router(booking_router)
    dp.include_router(my_appts_router)

    # ── Register admin router (with middleware) ──────────────────────────────────
    from aiogram import Router as AiRouter
    from handlers.admin.appointments import router as admin_appts_router
    from handlers.admin.menu import router as admin_menu_router
    from handlers.admin.services import router as admin_svc_router
    from handlers.admin.specialists import router as admin_sp_router
    from middlewares.auth import AdminMiddleware

    admin_router = AiRouter()
    admin_router.message.middleware(AdminMiddleware())
    admin_router.callback_query.middleware(AdminMiddleware())

    admin_router.include_router(admin_menu_router)
    admin_router.include_router(admin_appts_router)
    admin_router.include_router(admin_sp_router)
    admin_router.include_router(admin_svc_router)
    dp.include_router(admin_router)

    # ── APScheduler ──────────────────────────────────────────────────────────────
    from scheduler.reminders import scheduler, set_bot

    set_bot(bot)
    scheduler.start()
    logger.info("APScheduler started.")

    # ── Bot commands (menu) ───────────────────────────────────────────────────────
    from aiogram.types import BotCommand

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать / Главное меню"),
            BotCommand(command="my_appointments", description="Мои записи"),
            BotCommand(command="admin", description="Панель администратора"),
        ]
    )

    logger.info("Bot is starting polling…")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
