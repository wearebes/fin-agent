"""Authentication service: password hashing and JWT token management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from fin_agent.storage.user_store import UserInfo, UserStore


class AuthConfig:
    __slots__ = ("secret_key", "algorithm", "access_token_expire_minutes")

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60 * 24,
    ) -> None:
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


class AuthService:
    def __init__(self, user_store: UserStore, config: AuthConfig) -> None:
        self._store = user_store
        self._config = config

    def register(
        self,
        username: str,
        email: str,
        password: str,
        display_name: str,
    ) -> tuple[UserInfo, str]:
        if self._store.get_by_username(username) is not None:
            raise ValueError("Username already exists")
        if self._store.get_by_email(email) is not None:
            raise ValueError("Email already registered")

        hashed = hash_password(password)
        user = self._store.create_user(
            username=username,
            email=email,
            hashed_password=hashed,
            display_name=display_name,
        )
        token = self._create_token(user)
        return user, token

    def login(self, login_name: str, password: str) -> tuple[UserInfo, str]:
        user = self._store.get_by_username(login_name)
        if user is None:
            user = self._store.get_by_email(login_name)
        if user is None:
            raise ValueError("Invalid credentials")
        if not user.is_active:
            raise ValueError("Account is disabled")

        stored_hash = self._store.get_hashed_password(user.id)
        if stored_hash is None or not verify_password(password, stored_hash):
            raise ValueError("Invalid credentials")

        token = self._create_token(user)
        return user, token

    def get_current_user(self, token: str) -> UserInfo:
        payload = self._decode_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise ValueError("Invalid token")
        user = self._store.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        if not user.is_active:
            raise ValueError("Account is disabled")
        return user

    def update_profile(
        self,
        user_id: str,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> UserInfo:
        user = self._store.update_profile(
            user_id, display_name=display_name, avatar_url=avatar_url
        )
        if user is None:
            raise ValueError("User not found")
        return user

    def change_password(
        self, user_id: str, old_password: str, new_password: str
    ) -> bool:
        stored_hash = self._store.get_hashed_password(user_id)
        if stored_hash is None:
            raise ValueError("User not found")
        if not verify_password(old_password, stored_hash):
            raise ValueError("Old password is incorrect")
        hashed = hash_password(new_password)
        return self._store.update_password(user_id, hashed)

    def _create_token(self, user: UserInfo) -> str:
        expire = datetime.now(UTC) + timedelta(
            minutes=self._config.access_token_expire_minutes
        )
        payload = {
            "sub": user.id,
            "username": user.username,
            "exp": expire,
        }
        return jwt.encode(payload, self._config.secret_key, algorithm=self._config.algorithm)

    def _decode_token(self, token: str) -> dict:
        try:
            return jwt.decode(
                token,
                self._config.secret_key,
                algorithms=[self._config.algorithm],
            )
        except jwt.ExpiredSignatureError as exc:
            raise ValueError("Token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise ValueError("Invalid token") from exc
