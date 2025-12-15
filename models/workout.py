from datetime import date as date_type, time as time_type, datetime
from typing import Optional, List, Tuple

from sqlalchemy import (
    String,
    Date,
    Time,
    Float,
    Boolean,
    Table,
    Column,
    ForeignKey,
    Text,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from .user import User

workout_participants = Table(
    "workout_participants",
    Base.metadata,
    Column("workout_id", Integer, ForeignKey("workouts.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
)

workout_invited = Table(
    "workout_invited",
    Base.metadata,
    Column("workout_id", Integer, ForeignKey("workouts.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
)


class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    date: Mapped[date_type] = mapped_column(Date, nullable=False, comment="Дата тренировки (local)")
    time: Mapped[time_type] = mapped_column(
        Time, nullable=False, comment="Время тренировки (Московское локальное)"
    )

    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Широта")
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Долгота")

    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, default="", nullable=True)

    price: Mapped[Optional[float]] = mapped_column(Float, default=0.0, nullable=True)

    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    participants: Mapped[List[User]] = relationship(
        "User",
        secondary=workout_participants,
        backref="workouts",
        lazy="selectin",
    )

    users_invited: Mapped[List[User]] = relationship(
        "User",
        secondary=workout_invited,
        backref="invited_workouts",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Workout(id={self.id}, name='{self.name}', date={self.date}, time={self.time})>"

    @property
    def geo_location(self) -> Optional[Tuple[float, float]]:
        if self.latitude is None or self.longitude is None:
            return None
        return (self.latitude, self.longitude)

    @property
    def get_address(self) -> str:
        if self.latitude is None or self.longitude is None:
            return "Не указано"
        return f"Широта: {self.latitude}, Долгота: {self.longitude}"

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def has_name(self) -> bool:
        return bool(self.name)

    @property
    def has_comment(self) -> bool:
        return bool(self.comment)

    @property
    def has_price(self) -> bool:
        return bool(self.price)

    @property
    def start_datetime_moscow(self) -> datetime:
        return datetime.combine(self.date, self.time)

    def get_text_notification_tg(self) -> str:
        parts = [
            "Доступна новая тренировка!",
            f"*{self.name}*" if self.has_name else "",
            f"Дата: {self.date.strftime('%d.%m.%Y')}",
            f"Время: {self.time.strftime('%H:%M')}",
        ]

        if self.price and self.price > 0:
            parts.append(f"💰 Стоимость: {self.price}")
        else:
            parts.append("💰 Стоимость: бесплатно")

        if self.has_comment:
            parts.append(f"\nКомментарий:\n{self.comment}")

        return "\n".join(p for p in parts if p)

    def get_text_display_tg(self) -> str:
        parts = [
            f"*{self.name}*",
            f"Дата: {self.date.strftime('%d.%m.%Y')}",
            f"Время: {self.time.strftime('%H:%M')}",
        ]
        if self.has_location:
            parts.append(f"📍 {self.get_address}")
        if self.price and self.price > 0:
            parts.append(f"💰 Стоимость: {self.price}")
        else:
            parts.append("💰 Стоимость: бесплатно")
        if self.has_comment:
            parts.append(f"\nКомментарий:\n{self.comment}")
        if self.is_public:
            parts.append(f"\nТип тренировки: публичная")
            parts.append(f"\nПриглашены: Все")
        else:
            parts.append(f"\nТип тренировки: приватная")
            invited_names = [u.full_name for u in self.users_invited]
            parts.append(f"\nПриглашены: {', '.join(invited_names) if invited_names else 'никто'}")
        parts.append(f"\nУчастников: {len(self.participants)}")
        return "\n".join(parts)