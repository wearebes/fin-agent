"""Existing account capabilities and authentication errors, without external services."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fin_agent.interfaces.api.auth_router import build_auth_router
from fin_agent.services.auth import AuthConfig, AuthService
from fin_agent.storage.user_store import InMemoryUserStore


@pytest.fixture
def client():
    app = FastAPI()
    app.state.container = SimpleNamespace(
        auth_service=AuthService(
            InMemoryUserStore(),
            AuthConfig(secret_key="offline-test-signing-key-not-for-production"),
        )
    )
    app.include_router(build_auth_router())
    with TestClient(app) as test_client:
        yield test_client


def test_register_login_profile_and_password_remain_compatible(client):
    registered = client.post(
        "/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "old-password",
        },
    )
    assert registered.status_code == 200
    payload = registered.json()
    assert "hashed_password" not in payload["user"]
    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    assert client.get("/v1/auth/me", headers=headers).json()["username"] == "testuser"
    profile = client.patch("/v1/auth/profile", headers=headers, json={"display_name": "Updated"})
    assert profile.status_code == 200
    assert profile.json()["display_name"] == "Updated"
    bad_password = client.post(
        "/v1/auth/change-password",
        headers=headers,
        json={
            "old_password": "wrong-password",
            "new_password": "new-password",
        },
    )
    assert bad_password.status_code == 400
    changed = client.post(
        "/v1/auth/change-password",
        headers=headers,
        json={
            "old_password": "old-password",
            "new_password": "new-password",
        },
    )
    assert changed.status_code == 200
    for password, expected in [("old-password", 401), ("new-password", 200)]:
        assert (
            client.post(
                "/v1/auth/login",
                json={
                    "login_name": "testuser",
                    "password": password,
                },
            ).status_code
            == expected
        )


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/v1/auth/me", None),
        ("PATCH", "/v1/auth/profile", {"display_name": "Unauthorized"}),
        (
            "POST",
            "/v1/auth/change-password",
            {"old_password": "old", "new_password": "new-password"},
        ),
    ],
)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
def test_all_protected_account_endpoints_return_401(client, method, path, body, headers):
    assert client.request(method, path, json=body, headers=headers).status_code == 401
