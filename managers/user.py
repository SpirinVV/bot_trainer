from typing import Optional, List
from datetime import date

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User


class UserManager:
    def __init__(self, sessionmaker):
        self.sessionmaker = sessionmaker

    async def create(
        self,
        tg_id: int,
        first_name: str,
        last_name: Optional[str] = None,
        middle_name: Optional[str] = None,
        birth_date: Optional[date] = None,
        weight: Optional[float] = None,
        tg_username: Optional[str] = None
    ) -> User:
        async with self.sessionmaker() as session:
            user = User(
                tg_id=tg_id,
                first_name=first_name,
                last_name=last_name,
                middle_name=middle_name,
                birth_date=birth_date,
                weight=weight,
                tg_username=tg_username
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def get_by_id(self, user_id: int) -> Optional[User]:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            return result.scalar_one_or_none()

    async def get_by_tg_id(self, tg_id: int) -> Optional[User]:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[User]:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(User).limit(limit).offset(offset)
            )
            return list(result.scalars().all())

    async def update_weight(self, tg_id: int, weight: float) -> bool:
        async with self.sessionmaker() as session:
            result = await session.execute(
                update(User)
                .where(User.tg_id == tg_id)
                .values(weight=weight)
            )
            await session.commit()
            return result.rowcount > 0

    async def update_user(
        self,
        tg_id: int,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        middle_name: Optional[str] = None,
        birth_date: Optional[date] = None,
        weight: Optional[float] = None
    ) -> bool:
        values = {}
        if first_name is not None:
            values['first_name'] = first_name
        if last_name is not None:
            values['last_name'] = last_name
        if middle_name is not None:
            values['middle_name'] = middle_name
        if birth_date is not None:
            values['birth_date'] = birth_date
        if weight is not None:
            values['weight'] = weight

        if not values:
            return False

        async with self.sessionmaker() as session:
            result = await session.execute(
                update(User).where(User.tg_id == tg_id).values(**values)
            )
            await session.commit()
            return result.rowcount > 0

    async def update_user_by_id(
        self,
        user_id: int,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        middle_name: Optional[str] = None,
        birth_date: Optional[date] = None,
        weight: Optional[float] = None
    ) -> bool:
        values = {}
        if first_name is not None:
            values['first_name'] = first_name
        if last_name is not None:
            values['last_name'] = last_name
        if middle_name is not None:
            values['middle_name'] = middle_name
        if birth_date is not None:
            values['birth_date'] = birth_date
        if weight is not None:
            values['weight'] = weight

        if not values:
            return False

        async with self.sessionmaker() as session:
            result = await session.execute(
                update(User).where(User.id == user_id).values(**values)
            )
            await session.commit()
            return result.rowcount > 0

    async def delete(self, tg_id: int) -> bool:
        async with self.sessionmaker() as session:
            result = await session.execute(
                delete(User).where(User.tg_id == tg_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def exists(self, tg_id: int) -> bool:
        user = await self.get_by_tg_id(tg_id)
        return user is not None

    async def count(self) -> int:
        async with self.sessionmaker() as session:
            result = await session.execute(select(User))
            return len(list(result.scalars().all()))

    async def get_all_users(self, ids: List[int] = None) -> List[User]:
        if ids is None:
            ids = []

        async with self.sessionmaker() as session:
            if ids:
                result = await session.execute(select(User).where(User.id.in_(ids)))
            else:
                result = await session.execute(select(User))
            users = result.scalars().all()
            return users