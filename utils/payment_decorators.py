"""
Декораторы для проверки платежных деталей
"""
import logging
from functools import wraps
from typing import Callable, Any
from aiogram.types import Message, CallbackQuery

logger = logging.getLogger(__name__)


def requires_payment_info(func: Callable) -> Callable:
    """
    Декоратор для проверки наличия платежной информации (телефон и email)
    перед попыткой оплаты.
    
    Использование:
        @requires_payment_info
        async def handle_payment(message: Message, user: User):
            ...
    """
    @wraps(func)
    async def wrapper(obj: Any, *args, **kwargs) -> Any:
        # obj может быть Message или CallbackQuery
        from aiogram.types import Message, CallbackQuery
        
        user = None
        
        # Извлечь user из kwargs или из контекста
        if "user" in kwargs:
            user = kwargs["user"]
        else:
            # Пытаться получить из args
            for arg in args:
                if hasattr(arg, "first_name") and hasattr(arg, "tg_id"):
                    user = arg
                    break
        
        # Определить, откуда отправить сообщение
        if isinstance(obj, Message):
            message = obj
            callback = None
        elif isinstance(obj, CallbackQuery):
            callback = obj
            message = obj.message
        else:
            message = obj
            callback = None
        
        # Проверить данные пользователя
        if not user:
            if message:
                await message.answer(
                    "❌ Ошибка: не удалось получить данные пользователя"
                )
            return
        
        if not user.phone or not user.email:
            missing = []
            if not user.phone:
                missing.append("номер телефона")
            if not user.email:
                missing.append("email")
            
            text = (
                f"⚠️ Для оплаты необходимо указать: {' и '.join(missing)}\n\n"
                f"Пожалуйста, заполните профиль перед оплатой.\n"
                f"Используйте команду /profile"
            )
            
            if callback:
                await callback.answer(text, show_alert=True)
            elif message:
                await message.answer(text)
            return
        
        # Все хорошо, выполнить функцию
        return await func(obj, *args, **kwargs)
    
    return wrapper


def requires_payment_method(payment_method: str):
    """
    Декоратор для проверки выбранного способа оплаты
    
    Args:
        payment_method: 'TG' или 'LINK'
    
    Использование:
        @requires_payment_method('TG')
        async def handle_tg_payment(message: Message):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(obj: Any, *args, **kwargs) -> Any:
            kwargs["payment_method"] = payment_method
            return await func(obj, *args, **kwargs)
        return wrapper
    return decorator
