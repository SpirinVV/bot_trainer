import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import settings
from commands import register_handlers
from database import init_db, async_session_maker

from utils.admin import AdminPanel
from managers.user import UserManager


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    logger.info("🤖 Запуск Telegram бота...")

    logger.info("Инициализация базы данных...")
    await init_db()
    logger.info("✓ База данных инициализирована")

    user_manager = UserManager(async_session_maker)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    admin_panel = AdminPanel(user_manager=user_manager, bot=bot)
    from aiogram.fsm.storage.memory import MemoryStorage

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    register_handlers(dp, admin_panel)

    try:
        logger.info("✓ Бот успешно запущен и слушает обновления")
        logger.info("  - Bot Polling активен")
        logger.info("  - API доступен на http://api:8000 (в Docker сети)")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
