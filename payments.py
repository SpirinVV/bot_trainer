"""
Обработка платежей через Yookassa
"""
import logging
from typing import Optional
import uuid
from datetime import datetime
import json

from yookassa import Configuration, Payment
from pydantic import BaseModel
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database import async_session_maker
from managers.user import UserManager

logger = logging.getLogger(__name__)

# Инициализация Yookassa
Configuration.account_id = settings.YOOKASSA_ACCOUNT_ID
Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


class PaymentNotification(BaseModel):
    """Модель webhook уведомления от Yookassa"""
    type: str  # "notification"
    event: str  # "payment.succeeded", "payment.canceled" и т.д.
    object: dict  # Объект платежа


class PaymentService:
    """Сервис для работы с платежами"""

    @staticmethod
    async def create_payment(
        amount: float,
        description: str,
        return_url: str = "https://example.com/payment-success",
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        **metadata
    ) -> dict:
        """
        Создать платеж в Yookassa
        
        Args:
            amount: Сумма платежа в RUB
            description: Описание платежа
            return_url: URL для редиректа после платежа
            customer_email: Email покупателя
            customer_phone: Телефон покупателя
            **metadata: Дополнительные метаданные (user_id, order_id и т.д.)
        
        Returns:
            dict: Информация о созданном платеже
        """
        try:
            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url
                },
                "capture": True,
                "description": description,
                "metadata": metadata
            }

            # Добавить информацию клиента если есть
            if customer_email or customer_phone:
                payment_data["receipt"] = {
                    "customer": {},
                    "items": [
                        {
                            "description": description,
                            "quantity": 1,
                            "amount": {
                                "value": f"{amount:.2f}",
                                "currency": "RUB"
                            },
                            "vat_code": 1,
                            "payment_mode": "full_payment",
                            "payment_subject": "service"
                        }
                    ],
                    "tax_system_code": 1
                }
                if customer_email:
                    payment_data["receipt"]["customer"]["email"] = customer_email
                if customer_phone:
                    payment_data["receipt"]["customer"]["phone"] = customer_phone

            payment = Payment.create(payment_data, uuid.uuid4())
            
            logger.info(f"✓ Платеж создан: {payment.id}")
            
            return {
                "id": payment.id,
                "status": payment.status,
                "confirmation_url": payment.confirmation.confirmation_url if payment.confirmation else None,
                "amount": float(payment.amount.value),
                "created_at": payment.created_at.isoformat() if payment.created_at else None
            }
        except Exception as e:
            logger.error(f"❌ Ошибка создания платежа: {str(e)}")
            raise

    @staticmethod
    async def get_payment(payment_id: str) -> dict:
        """
        Получить информацию о платеже
        
        Args:
            payment_id: ID платежа
        
        Returns:
            dict: Информация о платеже
        """
        try:
            payment = Payment.find_one(payment_id)
            return {
                "id": payment.id,
                "status": payment.status,
                "amount": float(payment.amount.value),
                "paid": payment.paid,
                "created_at": payment.created_at.isoformat() if payment.created_at else None
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения платежа {payment_id}: {str(e)}")
            raise

    @staticmethod
    async def handle_webhook(notification: PaymentNotification, user_manager: UserManager) -> bool:
        """
        Обработать webhook от Yookassa
        
        Args:
            notification: Уведомление от Yookassa
            user_manager: Менеджер пользователей для обновления статуса
        
        Returns:
            bool: True если обработка успешна
        """
        logger.info(f"📬 Получено уведомление: {notification.event}")
        
        try:
            payment_obj = notification.object
            payment_id = payment_obj.get("id")
            event = notification.event
            status = payment_obj.get("status")
            
            logger.info(f"   ID платежа: {payment_id}")
            logger.info(f"   Статус: {status}")
            
            # Извлечь метаданные (user_id, order_id и т.д.)
            metadata = payment_obj.get("metadata", {})
            user_id = metadata.get("user_id")
            order_id = metadata.get("order_id")
            
            # Обработка успешного платежа
            if event == "payment.succeeded" and status == "succeeded":
                logger.info(f"✓ Платеж успешен: {payment_id}")
                
                if user_id:
                    # Обновить статус платежа в БД
                    async with async_session_maker() as session:
                        user = await user_manager.get_user(int(user_id))
                        if user:
                            logger.info(f"✓ Платеж обработан для пользователя {user_id}")
                            # TODO: Здесь добавить логику обновления статуса платежа в БД
                            # await user_manager.update_payment_status(user_id, payment_id, "completed")
                
                return True
            
            # Платеж отменён
            elif event == "payment.canceled" or status == "canceled":
                logger.warning(f"❌ Платеж отменён: {payment_id}")
                
                if user_id:
                    async with async_session_maker() as session:
                        logger.info(f"⚠️ Платеж отменён для пользователя {user_id}")
                        # TODO: Обновить статус в БД
                        # await user_manager.update_payment_status(user_id, payment_id, "canceled")
                
                return True
            
            # Платеж ожидает подтверждения
            elif event == "payment.waiting_for_capture":
                logger.info(f"⏳ Платеж ожидает подтверждения: {payment_id}")
                return True
            
            else:
                logger.warning(f"⚠️ Неизвестное событие: {event}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки webhook: {str(e)}", exc_info=True)
            # Возвращаем True чтобы Yookassa не повторял попытку
            return True


class WorkoutPaymentHelper:
    """Помощник для управления платежами при записи на тренировку"""
    
    @staticmethod
    def get_payment_keyboard(workout_id: int, user_id: int, price: float) -> Optional[InlineKeyboardMarkup]:
        """
        Получить клавиатуру с кнопками оплаты
        
        Args:
            workout_id: ID тренировки
            user_id: ID пользователя
            price: Стоимость тренировки
        
        Returns:
            InlineKeyboardMarkup с кнопками оплаты или None если бесплатно
        """
        if not price or price <= 0:
            return None
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Оплатить (TG)",
                    callback_data=f"pay_tg:{workout_id}:{user_id}"
                ),
                InlineKeyboardButton(
                    text="💰 Оплатить (СБП)",
                    callback_data=f"pay_link:{workout_id}:{user_id}"
                )
            ]
        ])
        return kb
    
    @staticmethod
    def create_payment_details(
        payment_method: str,
        status: str = "pending",
        payment_id: Optional[str] = None,
        timestamp: Optional[str] = None
    ) -> dict:
        """
        Создать объект деталей платежа
        
        Args:
            payment_method: 'TG' или 'LINK'
            status: 'success', 'pending', 'failed'
            payment_id: ID платежа в Yookassa
            timestamp: Время платежа
        
        Returns:
            dict: Объект с деталями платежа
        """
        return {
            "payment_method": payment_method,
            "status": status,
            "payment_id": payment_id,
            "timestamp": timestamp or datetime.utcnow().isoformat()
        }
    
    @staticmethod
    async def send_payment_confirmation(
        bot: Bot,
        user_id: int,
        workout_name: str,
        price: float,
        payment_method: str
    ):
        """
        Отправить пользователю подтверждение записи на тренировку
        
        Args:
            bot: Экземпляр Telegram бота
            user_id: ID пользователя (tg_id)
            workout_name: Название тренировки
            price: Цена тренировки
            payment_method: Способ оплаты (TG или LINK)
        """
        method_name = "Telegram Pay" if payment_method == "TG" else "СБП/Ссылка"
        
        text = (
            f"✅ <b>Отлично!</b> Вы успешно записались на тренировку!\n\n"
            f"📝 <b>{workout_name}</b>\n"
            f"💰 Стоимость: <b>{price} ₽</b>\n"
            f"💳 Способ оплаты: <b>{method_name}</b>\n\n"
            f"Спасибо за участие! 🎉"
        )
        
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
            logger.info(f"✓ Подтверждение отправлено пользователю {user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки подтверждения: {str(e)}")
