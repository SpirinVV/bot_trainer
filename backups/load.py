import os
import sys
import logging
from datetime import datetime, date as date_type
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from models.user import User
from models.workout import Workout

# ─── Конфигурация ────────────────────────────────────────────────────────────

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/service_account.json")
SPREADSHEET_ID              = os.getenv("SPREADSHEET_ID", "")
DATABASE_URL                = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/bot.db")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def safe(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, date_type):
        return value.strftime("%d.%m.%Y")
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
    ws = get_or_create_worksheet(spreadsheet, title)
    ws.clear()
    if not rows:
        return
    ws.update("A1", rows, value_input_option="USER_ENTERED")

    header_range = f"A1:{chr(ord('A') + len(rows[0]) - 1)}1"
    ws.format(header_range, {
        "backgroundColor": {"red": 0.26, "green": 0.52, "blue": 0.96},
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "horizontalAlignment": "CENTER",
    })
    ws.freeze(rows=1)

    log.info("Лист '%-20s': %d строк", title, len(rows) - 1)


# ─── Данные ──────────────────────────────────────────────────────────────────

async def build_users_rows(session: AsyncSession) -> list[list]:
    headers = [
        "ID", "Telegram ID", "Username",
        "Имя", "Фамилия", "Отчество",
        "Дата рождения", "Возраст", "Вес (кг)",
        "Телефон", "Email",
        "Зарегистрирован", "Обновлён",
    ]
    rows = [headers]
    result = await session.scalars(select(User).order_by(User.id))
    for u in result:
        rows.append([
            safe(u.id),
            safe(u.tg_id),
            f"@{u.tg_username}" if u.tg_username else "—",
            safe(u.first_name),
            safe(u.last_name),
            safe(u.middle_name),
            safe(u.birth_date),
            safe(u.age),
            safe(u.weight),
            safe(u.phone),
            safe(u.email),
            safe(u.created_at),
            safe(u.updated_at),
        ])
    return rows


async def build_workouts_rows(session: AsyncSession) -> list[list]:
    headers = [
        "ID", "Название", "Дата", "Время",
        "Тип", "Цена (руб.)", "Участников", "Приглашено",
        "Комментарий",
    ]
    rows = [headers]
    result = await session.scalars(select(Workout).order_by(Workout.date, Workout.time))
    for w in result:
        rows.append([
            safe(w.id),
            safe(w.name),
            safe(w.date),
            w.time.strftime("%H:%M"),
            "Публичная" if w.is_public else "Приватная",
            safe(w.price) if w.price else "Бесплатно",
            len(w.participants),
            len(w.users_invited),
            safe(w.comment),
        ])
    return rows


async def build_participants_rows(session: AsyncSession) -> list[list]:
    headers = [
        "ID тренировки", "Тренировка", "Дата", "Время",
        "ID клиента", "ФИО", "Username", "Роль",
    ]
    rows = [headers]
    result = await session.scalars(select(Workout).order_by(Workout.date, Workout.time))
    for w in result:
        for u in w.participants:
            rows.append([
                safe(w.id), safe(w.name), safe(w.date), w.time.strftime("%H:%M"),
                safe(u.id), safe(u.full_name),
                f"@{u.tg_username}" if u.tg_username else "—",
                "Участник",
            ])
        for u in w.users_invited:
            rows.append([
                safe(w.id), safe(w.name), safe(w.date), w.time.strftime("%H:%M"),
                safe(u.id), safe(u.full_name),
                f"@{u.tg_username}" if u.tg_username else "—",
                "Приглашён",
            ])
    return rows


# ─── Точка входа ─────────────────────────────────────────────────────────────

async def main():
    log.info("=== Синхронизация с Google Sheets начата ===")

    engine = create_async_engine(DATABASE_URL, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        log.info("Читаем данные из БД...")
        users_rows        = await build_users_rows(session)
        workouts_rows     = await build_workouts_rows(session)
        participants_rows = await build_participants_rows(session)

    log.info(
        "Получено: %d пользователей, %d тренировок, %d записей участников",
        len(users_rows) - 1,
        len(workouts_rows) - 1,
        len(participants_rows) - 1,
    )

    log.info("Авторизация в Google...")
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    write_sheet(spreadsheet, "Пользователи", users_rows)
    write_sheet(spreadsheet, "Тренировки",   workouts_rows)
    write_sheet(spreadsheet, "Участники",    participants_rows)

    log.info("=== Готово ===")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
