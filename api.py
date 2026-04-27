"""
FastAPI приложение для обработки webhook'ов Yookassa
"""
import logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import sys
from pathlib import Path

# Добавить родительскую директорию в path для импортов
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from payments import PaymentService, PaymentNotification
from database import async_session_maker, init_db
from config import settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Bot Trainer Payments API")

bot: Bot = None


@app.on_event("startup")
async def startup_event():
    global bot
    logger.info("🚀 Инициализация FastAPI сервера...")
    try:
        await init_db()
        logger.info("✓ База данных инициализирована")
    except Exception as e:
        logger.warning(f"⚠️ БД уже инициализирована: {str(e)}")
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    logger.info("✓ Bot instance создан для уведомлений")


@app.on_event("shutdown")
async def shutdown_event():
    global bot
    if bot:
        await bot.session.close()


@app.post("/webhook/yookassa")
async def yookassa_webhook(request: Request) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"🔔 Webhook от {client_ip}")
    try:
        body = await request.json()
        logger.info(f"   event={body.get('event')} payment_id={body.get('object', {}).get('id')} status={body.get('object', {}).get('status')}")
        
        # Создать объект уведомления
        notification = PaymentNotification(**body)
        
        # Обработать webhook
        success = await PaymentService.handle_webhook(notification, bot)
        
        if success:
            return Response(status_code=200)
        else:
            logger.error("❌ Ошибка обработки webhook")
            return Response(status_code=200)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка webhook: {str(e)}", exc_info=True)
        return Response(status_code=200)


@app.post("/api/payment/create")
async def create_payment_endpoint(
    amount: float,
    description: str,
    return_url: str = "https://example.com/payment-success",
    customer_email: str = None,
    customer_phone: str = None
) -> dict:
    """
    REST API endpoint для создания платежа
    
    Args:
        amount: Сумма платежа в RUB
        description: Описание платежа
        return_url: URL для редиректа после платежа
        customer_email: Email покупателя
        customer_phone: Телефон покупателя
    
    Returns:
        dict с информацией о платеже и ссылкой для оплаты
    """
    try:
        payment = await PaymentService.create_payment(
            amount=amount,
            description=description,
            return_url=return_url,
            customer_email=customer_email,
            customer_phone=customer_phone
        )
        return {
            "status": "success",
            "data": payment
        }
    except Exception as e:
        logger.error(f"❌ Ошибка создания платежа: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/api/payment/{payment_id}")
async def get_payment_endpoint(payment_id: str) -> dict:
    """
    REST API endpoint для получения информации о платеже
    
    Args:
        payment_id: ID платежа Yookassa
    
    Returns:
        dict с информацией о платеже
    """
    try:
        payment = await PaymentService.get_payment(payment_id)
        return {
            "status": "success",
            "data": payment
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения платежа: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint"""
    return {"status": "ok", "service": "trainer_api"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Запустить FastAPI сервер на localhost:8000
    # Для production используйте nginx/Apache для proxy'ing на HTTPS
    uvicorn.run(app, host="0.0.0.0", port=8000)
