import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
import logging
import time
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError

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

    from aiohttp import ClientTimeout
    from aiogram.client.session.aiohttp import AiohttpSession

    session = AiohttpSession(
        timeout=ClientTimeout(total=30, connect=10)
    )

    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    admin_panel = AdminPanel(user_manager=user_manager, bot=bot)
    from aiogram.fsm.storage.memory import MemoryStorage

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    register_handlers(dp, admin_panel)

    retry_delay = 5
    attempt = 0

    try:
        while True:
            attempt += 1
            try:
                logger.info(f"✓ Бот запускается (попытка {attempt})")
                logger.info("  - Bot Polling активен")
                logger.info("  - API доступен на http://api:8000 (в Docker сети)")
                await dp.start_polling(
                    bot,
                    timeout=25,  # shorter than typical NAT/firewall 30s cutoff
                    allowed_updates=dp.resolve_used_update_types(),
                )
                break
            except TelegramNetworkError as e:
                logger.error(f"❌ Сетевая ошибка: {e}")
                logger.info(f"⏳ Переподключение через {retry_delay} сек...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 30)
            except Exception as e:
                logger.error(f"❌ Неизвестная ошибка: {e}", exc_info=True)
                logger.info(f"⏳ Переподключение через {retry_delay} сек...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 30)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
