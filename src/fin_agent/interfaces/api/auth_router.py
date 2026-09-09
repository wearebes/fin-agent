"""HTTP routes for user authentication and profile management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from fin_agent.storage.user_store import UserInfo


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="Username")
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=6, max_length=128, description="Password")
    display_name: str = Field(default="", max_length=128, description="Display name")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v


class LoginRequest(BaseModel):
    login_name: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=512)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=6, max_length=128, description="New password")


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    display_name: str
    avatar_url: str | None
    is_active: bool
    created_at: str
    updated_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def _user_to_response(user: UserInfo) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
        updated_at=user.updated_at.isoformat() if user.updated_at else "",
    )


def _extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    return auth_header[7:]


def _get_current_user(request: Request) -> UserInfo:
    """Classify authentication failures consistently before business validation."""
    token = _extract_token(request)
    try:
        return request.app.state.container.auth_service.get_current_user(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def build_auth_router() -> APIRouter:
    router = APIRouter()

    @router.post("/v1/auth/register", response_model=TokenResponse, tags=["auth"])
    def register(payload: RegisterRequest, request: Request) -> TokenResponse:
        auth_service = request.app.state.container.auth_service
        try:
            user, token = auth_service.register(
                username=payload.username,
                email=payload.email,
                password=payload.password,
                display_name=payload.display_name or payload.username,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            ) from e
        return TokenResponse(access_token=token, user=_user_to_response(user))

    @router.post("/v1/auth/login", response_model=TokenResponse, tags=["auth"])
    def login(payload: LoginRequest, request: Request) -> TokenResponse:
        auth_service = request.app.state.container.auth_service
        try:
            user, token = auth_service.login(
                login_name=payload.login_name,
                password=payload.password,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
            ) from e
        return TokenResponse(access_token=token, user=_user_to_response(user))

    @router.get("/v1/auth/me", response_model=UserResponse, tags=["auth"])
    def get_current_user(request: Request) -> UserResponse:
        return _user_to_response(_get_current_user(request))

    @router.patch("/v1/auth/profile", response_model=UserResponse, tags=["auth"])
    def update_profile(payload: UpdateProfileRequest, request: Request) -> UserResponse:
        auth_service = request.app.state.container.auth_service
        current_user = _get_current_user(request)
        try:
            user = auth_service.update_profile(
                current_user.id,
                display_name=payload.display_name,
                avatar_url=payload.avatar_url,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            ) from e
        return _user_to_response(user)

    @router.post("/v1/auth/change-password", tags=["auth"])
    def change_password(payload: ChangePasswordRequest, request: Request) -> dict[str, str]:
        auth_service = request.app.state.container.auth_service
        current_user = _get_current_user(request)
        try:
            auth_service.change_password(
                current_user.id,
                old_password=payload.old_password,
                new_password=payload.new_password,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e
        return {"detail": "Password changed successfully"}

    return router
