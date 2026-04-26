"""
Декораторы для проверки платёжных данных перед оплатой по СБП.
"""
import logging
from functools import wraps
from aiogram.types import CallbackQuery

logger = logging.getLogger(__name__)


def requires_payment_info(func):
    """
    Проверяет наличие phone и email у пользователя перед оплатой по СБП.
    Применяется к callback-хендлерам (методам класса или обычным функциям).
    При отсутствии данных показывает alert и прерывает выполнение.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Найти CallbackQuery среди аргументов (поддерживает и self.method, и обычную функцию)
        callback: CallbackQuery = None
        for arg in args:
            if isinstance(arg, CallbackQuery):
                callback = arg
                break

        if callback is None:
            return await func(*args, **kwargs)

        from database import async_session_maker
        from managers.user import UserManager

        user = await UserManager(async_session_maker).get_by_tg_id(callback.from_user.id)

        if not user:
            await callback.answer("❌ Пользователь не найден в системе.", show_alert=True)
            return

        if not user.phone or not user.email:
            missing = []
            if not user.phone:
                missing.append("номер телефона")
            if not user.email:
                missing.append("email")
            await callback.answer(
                f"⚠️ Для оплаты по СБП необходимо указать: {' и '.join(missing)}.\n\n"
                f"Обновите данные через /profile → ✏️ Редактировать",
                show_alert=True,
            )
            return

        return await func(*args, **kwargs)

    return wrapper
