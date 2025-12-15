import os
from dataclasses import dataclass
from typing import List
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    BOT_TOKEN: str
    PAYMENT_TOKEN: str
    DATABASE_URL: str
    OWNER_ID: int
    ADMIN_IDS: List[int]
    GARMIN_EMAIL: str
    GARMIN_PASSWORD: str

    def __post_init__(self):
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не может быть пустым")

        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL не может быть пустым")

        if self.OWNER_ID not in self.ADMIN_IDS:
            self.ADMIN_IDS.append(self.OWNER_ID)


def load_settings() -> Settings:
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    admin_ids = []
    if admin_ids_str:
        try:
            admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
        except ValueError:
            print("Ошибка при парсинге ADMIN_IDS, используется пустой список")
    return Settings(
        BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
        PAYMENT_TOKEN=os.getenv("PAYMENT_TOKEN", ""),
        DATABASE_URL=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db"),
        OWNER_ID=int(os.getenv("OWNER_ID", "0")),
        ADMIN_IDS=admin_ids,
        GARMIN_EMAIL=os.getenv("GARMIN_EMAIL", ""),
        GARMIN_PASSWORD=os.getenv("GARMIN_PASSWORD", "")
    )


settings = load_settings()
