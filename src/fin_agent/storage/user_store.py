"""Storage primitives for user persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fin_agent.storage.models import Base, UserRow


class UserInfo:
    __slots__ = (
        "id",
        "username",
        "email",
        "display_name",
        "avatar_url",
        "is_active",
        "created_at",
        "updated_at",
    )

    def __init__(
        self,
        *,
        id: str,
        username: str,
        email: str,
        display_name: str,
        avatar_url: str | None,
        is_active: bool,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        self.id = id
        self.username = username
        self.email = email
        self.display_name = display_name
        self.avatar_url = avatar_url
        self.is_active = is_active
        self.created_at = created_at
        self.updated_at = updated_at


class UserStore(Protocol):
    def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        display_name: str,
    ) -> UserInfo: ...

    def get_by_username(self, username: str) -> UserInfo | None: ...

    def get_by_email(self, email: str) -> UserInfo | None: ...

    def get_by_id(self, user_id: str) -> UserInfo | None: ...

    def get_hashed_password(self, user_id: str) -> str | None: ...

    def update_profile(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> UserInfo | None: ...

    def update_password(
        self,
        user_id: str,
        hashed_password: str,
    ) -> bool: ...


def _row_to_info(row: UserRow) -> UserInfo:
    return UserInfo(
        id=row.id,
        username=row.username,
        email=row.email,
        display_name=row.display_name,
        avatar_url=row.avatar_url,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SQLAlchemyUserStore:
    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self._engine = create_engine(database_url, echo=echo)

    def create_tables(self) -> None:
        Base.metadata.create_all(self._engine)

    def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        display_name: str,
    ) -> UserInfo:
        user_id = uuid4().hex
        row = UserRow(
            id=user_id,
            username=username,
            email=email,
            hashed_password=hashed_password,
            display_name=display_name,
            is_active=True,
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _row_to_info(row)

    def get_by_username(self, username: str) -> UserInfo | None:
        with Session(self._engine) as session:
            row = session.query(UserRow).filter(UserRow.username == username).first()
            if row is None:
                return None
            return _row_to_info(row)

    def get_by_email(self, email: str) -> UserInfo | None:
        with Session(self._engine) as session:
            row = session.query(UserRow).filter(UserRow.email == email).first()
            if row is None:
                return None
            return _row_to_info(row)

    def get_by_id(self, user_id: str) -> UserInfo | None:
        with Session(self._engine) as session:
            row = session.get(UserRow, user_id)
            if row is None:
                return None
            return _row_to_info(row)

    def get_hashed_password(self, user_id: str) -> str | None:
        with Session(self._engine) as session:
            row = session.get(UserRow, user_id)
            if row is None:
                return None
            return row.hashed_password

    def update_profile(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> UserInfo | None:
        with Session(self._engine) as session:
            row = session.get(UserRow, user_id)
            if row is None:
                return None
            if display_name is not None:
                row.display_name = display_name
            if avatar_url is not None:
                row.avatar_url = avatar_url
            session.commit()
            session.refresh(row)
            return _row_to_info(row)

    def update_password(
        self,
        user_id: str,
        hashed_password: str,
    ) -> bool:
        with Session(self._engine) as session:
            row = session.get(UserRow, user_id)
            if row is None:
                return False
            row.hashed_password = hashed_password
            session.commit()
            return True

    @property
    def engine(self):
        return self._engine


class InMemoryUserStore:
    def __init__(self) -> None:
        self._users: dict[str, UserRow] = {}
        self._username_index: dict[str, str] = {}
        self._email_index: dict[str, str] = {}

    def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        display_name: str,
    ) -> UserInfo:
        user_id = uuid4().hex
        now = datetime.now()
        row = UserRow(
            id=user_id,
            username=username,
            email=email,
            hashed_password=hashed_password,
            display_name=display_name,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self._users[user_id] = row
        self._username_index[username] = user_id
        self._email_index[email] = user_id
        return _row_to_info(row)

    def get_by_username(self, username: str) -> UserInfo | None:
        user_id = self._username_index.get(username)
        if user_id is None:
            return None
        row = self._users.get(user_id)
        return _row_to_info(row) if row else None

    def get_by_email(self, email: str) -> UserInfo | None:
        user_id = self._email_index.get(email)
        if user_id is None:
            return None
        row = self._users.get(user_id)
        return _row_to_info(row) if row else None

    def get_by_id(self, user_id: str) -> UserInfo | None:
        row = self._users.get(user_id)
        return _row_to_info(row) if row else None

    def get_hashed_password(self, user_id: str) -> str | None:
        row = self._users.get(user_id)
        if row is None:
            return None
        return row.hashed_password

    def update_profile(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> UserInfo | None:
        row = self._users.get(user_id)
        if row is None:
            return None
        if display_name is not None:
            row.display_name = display_name
        if avatar_url is not None:
            row.avatar_url = avatar_url
        row.updated_at = datetime.now()
        return _row_to_info(row)

    def update_password(
        self,
        user_id: str,
        hashed_password: str,
    ) -> bool:
        row = self._users.get(user_id)
        if row is None:
            return False
        row.hashed_password = hashed_password
        row.updated_at = datetime.now()
        return True
