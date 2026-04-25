from datetime import datetime, date
from typing import Optional

from sqlalchemy import BigInteger, String, Date, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)

    tg_username: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, unique=True, index=True)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    middle_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Вес в кг")
    
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="Номер телефона")
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Email адрес")

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, tg_id={self.tg_id}, name='{self.first_name}')>"

    @property
    def full_name(self) -> str:
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(part for part in parts if part)

    @property
    def age(self) -> Optional[int]:
        if not self.birth_date:
            return None

        today = date.today()
        age = today.year - self.birth_date.year

        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            age -= 1

        return age

    @property
    def editable_fields(self) -> dict:
        return {
            "first_name": self.first_name or "—",
            "last_name": self.last_name or "—",
            "middle_name": self.middle_name or "—",
            "birth_date": self.birth_date.strftime("%d.%m.%Y") if self.birth_date else "—",
            "weight": f"{self.weight} кг" if self.weight else "—"
        }

    @property
    def editable_fields_display(self) -> dict:
        return {
            "first_name": "Имя",
            "last_name": "Фамилия",
            "middle_name": "Отчество",
            "birth_date": "Дата рождения",
            "weight": "Вес"
        }

    def get_text_display_tg(self):

        if self.tg_username:
            name_link = f"[{self.full_name}](https://t.me/{self.tg_username})"
        else:
            name_link = self.full_name

        return (
            f"👤 Детали пользователя:\n"
            f"{name_link}\n\n"
            f"Возраст: {self.age}\n"
            f"Вес: {self.weight}"
        )


    def __str__(self):
        return self.full_name
