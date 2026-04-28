import asyncio
from datetime import date

import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.workout import Workout

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


async def generate_workouts_report(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    service_account_file: str,
    spreadsheet_id: str,
) -> str:
    result = await session.execute(
        select(Workout)
        .where(and_(Workout.date >= start_date, Workout.date <= end_date))
        .order_by(Workout.date, Workout.time)
    )
    workouts = list(result.scalars().all())

    headers = ["Дата", "Тип тренировки", "Название", "Клиенты", "Кол-во клиентов", "Стоимость"]
    rows: list[list] = [headers]
    total_participants = 0
    total_revenue = 0.0

    for w in workouts:
        clients = ", ".join(u.full_name for u in w.participants)
        count = len(w.participants)
        price = (w.price or 0.0) * count
        total_participants += count
        total_revenue += price
        rows.append([
            f"{w.date.strftime('%d.%m.%Y')} {w.time.strftime('%H:%M')}",
            "Публичная" if w.is_public else "Приватная",
            w.name,
            clients,
            count,
            price,
        ])

    rows.append([])
    rows.append([
        "Итого:",
        f"Тренировок: {len(workouts)}",
        "",
        "",
        f"Записей: {total_participants}",
        f"{total_revenue:.2f} руб.",
    ])

    sheet_name = f"{start_date.strftime('%d.%m.%Y')}—{end_date.strftime('%d.%m.%Y')}"
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(
        None, _write_to_spreadsheet, spreadsheet_id, sheet_name, rows, service_account_file
    )
    return url


def _write_to_spreadsheet(
    spreadsheet_id: str, sheet_name: str, rows: list, service_account_file: str
) -> str:
    creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
    gc = gspread.authorize(creds)

    spreadsheet = gc.open_by_key(spreadsheet_id)

    try:
        ws = spreadsheet.worksheet(sheet_name)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=len(rows) + 10, cols=10)

    data_rows = len(rows)
    ws.update("A1", rows, value_input_option="USER_ENTERED")

    # Заголовок
    ws.format("A1:F1", {
        "backgroundColor": {"red": 0.26, "green": 0.52, "blue": 0.96},
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "horizontalAlignment": "CENTER",
    })
    ws.freeze(rows=1)

    # Строка итогов
    total_row = data_rows
    ws.format(f"A{total_row}:F{total_row}", {
        "backgroundColor": {"red": 0.85, "green": 0.92, "blue": 0.76},
        "textFormat": {"bold": True},
    })

    # Чередование строк одним batch-запросом
    stripe_fmt = {"backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}}
    batch = [{"range": f"A{i}:F{i}", "format": stripe_fmt} for i in range(2, data_rows - 1) if i % 2 == 0]
    if batch:
        ws.batch_format(batch)

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={ws.id}"
