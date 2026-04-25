"""
schedule_backup.py
──────────────────
SqlAlchemy to gspread
"""

import os
import sys
import logging
import schedule
import time
from datetime import datetime

from load import main
import asyncio
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Создаем директорию для логов если её нет
log_dir = '/app/backups'
os.makedirs(log_dir, exist_ok=True)

# Конфигурируем логирование
handlers = [logging.StreamHandler()]
try:
    log_file = os.path.join(log_dir, 'backup.log')
    handlers.append(logging.FileHandler(log_file))
except Exception as e:
    print(f"⚠️ Не удалось создать лог файл: {e}")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)


def run_backup():
    try:
        logger.info("=" * 60)
        logger.info("🔄 Запуск резервного копи  рования в %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("=" * 60)
        
        asyncio.run(main())
        
        logger.info("✅ Резервное копирование завершено успешно")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("❌ Ошибка при резервном копировании: %s", str(e), exc_info=True)
        logger.info("=" * 60)


def schedule_backup():
    do_backups = os.getenv("DO_BACKUPS", "False").lower() == "true"
    
    if not do_backups:
        logger.warning("⚠️  DO_BACKUPS отключен. Резервное копирование не будет выполняться.")
        logger.info("Для включения установите DO_BACKUPS=True в .env файле")
        while True:
            time.sleep(300)  
    
    schedule.every().day.at("23:00").do(run_backup)
    logger.info("📅 Резервное копирование запланировано на 23:00 каждый день")
    
    while True:
        schedule.run_pending()
        time.sleep(60) 


if __name__ == "__main__":
    logger.info("🚀 Запуск планировщика резервного копирования")
    logger.info("Часовой пояс: %s", os.getenv("TZ", "Europe/Moscow"))
    
    do_backups = os.getenv("DO_BACKUPS", "False").lower() == "true"
    logger.info("DO_BACKUPS: %s", "✅ Включен" if do_backups else "❌ Отключен")
    
    try:
        schedule_backup()
    except KeyboardInterrupt:
        logger.info("⏹️  Планировщик остановлен")
        sys.exit(0)
