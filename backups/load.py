"""
sync_to_sheets.py
─────────────────
Ежедневный скрипт (23:00): читает данные из SQLAlchemy БД
и полностью перезаписывает Google Таблицу (3 листа).

Листы:
  1. Users           — все пользователи
  2. Workouts        — все тренировки
  3. Participants    — участники и приглашённые

Установка:
  pip install gspread google-auth sqlalchemy

Настройка Google:
  1. console.cloud.google.com → проект → включить Sheets API + Drive API
  2. IAM → Service Accounts → создать → скачать JSON-ключ → положить рядом как service_account.json
  3. Google Таблица → Поделиться → вставить client_email из JSON-ключа (Editor)
"""

import os
import sys
import logging
from datetime import datetime
from typing import Any

# Добавляем родительскую директорию в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from models.user import User
from models.workout import Workout
#pip install gspread google-auth sqlalchemy
# ─── Конфигурация ────────────────────────────────────────────────────────────

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/service_account.json")
SPREADSHEET_ID              = os.getenv("SPREADSHEET_ID", "")
DATABASE_URL                = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/bot.db")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def safe(value: Any) -> str:
    """Любое значение → строка. None → пустая строка."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def get_gspread_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_or_create_worksheet(spreadsheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=5000, cols=30)
        log.info("Создан новый лист: %s", title)
        return ws


def write_sheet(spreadsheet: gspread.Spreadsheet, title: str, rows: list[list]):
    """Очищает лист и записывает rows. Создаёт лист если не существует."""
    ws = get_or_create_worksheet(spreadsheet, title)
    ws.clear()
    if rows:
        ws.update("A1", rows, value_input_option="USER_ENTERED")
    log.info("Лист '%-14s': %d строк (включая заголовок)", title, len(rows))


# ─── Сборка данных ───────────────────────────────────────────────────────────

async def build_users_rows(session: AsyncSession) -> list[list]:
    headers = [
        "id", "tg_id", "tg_username",
        "first_name", "last_name", "middle_name",
        "birth_date", "age", "weight_kg",
        "created_at", "updated_at",
    ]
    rows = [headers]
    result = await session.scalars(select(User).order_by(User.id))
    for u in result:
        rows.append([
            safe(u.id),
            safe(u.tg_id),
            safe(u.tg_username),
            safe(u.first_name),
            safe(u.last_name),
            safe(u.middle_name),
            safe(u.birth_date),
            safe(u.age),
            safe(u.weight),
            safe(u.created_at),
            safe(u.updated_at),
        ])
    return rows


async def build_workouts_rows(session: AsyncSession) -> list[list]:
    headers = [
        "id", "name", "date", "time",
        "latitude", "longitude",
        "price", "is_public", "comment",
        "participants_count", "invited_count",
    ]
    rows = [headers]
    result = await session.scalars(select(Workout).order_by(Workout.date, Workout.time))
    for w in result:
        rows.append([
            safe(w.id),
            safe(w.name),
            safe(w.date),
            safe(w.time),
            safe(w.latitude),
            safe(w.longitude),
            safe(w.price),
            "да" if w.is_public else "нет",
            safe(w.comment),
            len(w.participants),
            len(w.users_invited),
        ])
    return rows


async def build_participants_rows(session: AsyncSession) -> list[list]:
    """
    Один лист — и участники (role=участник), и приглашённые (role=приглашён).
    Удобно фильтровать по колонке role прямо в таблице.
    """
    headers = [
        "workout_id", "workout_name", "workout_date", "workout_time",
        "user_id", "full_name", "tg_username", "role",
    ]
    rows = [headers]
    result = await session.scalars(select(Workout).order_by(Workout.date, Workout.time))
    for w in result:
        for u in w.participants:
            rows.append([
                safe(w.id), safe(w.name), safe(w.date), safe(w.time),
                safe(u.id), safe(u.full_name), safe(u.tg_username),
                "участник",
            ])
        for u in w.users_invited:
            rows.append([
                safe(w.id), safe(w.name), safe(w.date), safe(w.time),
                safe(u.id), safe(u.full_name), safe(u.tg_username),
                "приглашён",
            ])
    return rows


# ─── Точка входа ─────────────────────────────────────────────────────────────

async def main():
    log.info("=== Синхронизация с Google Sheets начата ===")

    # 1. Читаем всё из БД одной сессией
    engine = create_async_engine(DATABASE_URL, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        log.info("Читаем данные из БД...")
        users_rows        = await build_users_rows(session)
        workouts_rows     = await build_workouts_rows(session)
        participants_rows = await build_participants_rows(session)

    log.info(
        "Получено: %d пользователей, %d тренировок, %d строк участников",
        len(users_rows) - 1,
        len(workouts_rows) - 1,
        len(participants_rows) - 1,
    )

    # 2. Авторизация в Google
    log.info("Авторизация в Google...")
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    # 3. Записываем листы
    write_sheet(spreadsheet, "Users",        users_rows)
    write_sheet(spreadsheet, "Workouts",     workouts_rows)
    write_sheet(spreadsheet, "Participants", participants_rows)

    log.info("=== Готово ===")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())