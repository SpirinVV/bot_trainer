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
    PAYMENT_TOKEN_TG: str
    DATABASE_URL: str
    OWNER_ID: int
    ADMIN_IDS: List[int]
    GARMIN_EMAIL: str
    GARMIN_PASSWORD: str
    PAYMENT_MODE: str
    YOOKASSA_ACCOUNT_ID: str
    YOOKASSA_SECRET_KEY: str
    API_PORT: int

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
    if os.getenv('TEST_MODE', False):
        payment_token_tg = os.getenv("PAYMENT_TOKEN_TG_TEST", "")
    else:
        payment_token_tg = os.getenv("PAYMENT_TOKEN_TG", "")


    return Settings(
        BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
        PAYMENT_TOKEN=os.getenv("PAYMENT_TOKEN", ""),
        PAYMENT_TOKEN_TG=payment_token_tg,
        DATABASE_URL=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db"),
        OWNER_ID=int(os.getenv("OWNER_ID", "0")),
        ADMIN_IDS=admin_ids,
        GARMIN_EMAIL=os.getenv("GARMIN_EMAIL", ""),
        GARMIN_PASSWORD=os.getenv("GARMIN_PASSWORD", ""),
        PAYMENT_MODE=os.getenv("PAYMENT_MODE", "TG"),
        YOOKASSA_ACCOUNT_ID=os.getenv("YOOKASSA_ACCOUNT_ID", ""),
        YOOKASSA_SECRET_KEY=os.getenv("YOOKASSA_SECRET_KEY", ""),
        API_PORT=int(os.getenv("API_PORT", "8000")),
    )


settings = load_settings()
