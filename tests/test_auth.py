import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from data_upload.euphrosyne.auth import (
    EuphrosyneAuth,
    EuphrosyneConnectionError,
    euphrosyne_login,
    is_token_expired,
    refresh_token,
)


class FakeSettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value


def _jwt_with_payload(payload: dict) -> str:
    encoded_payload = (
        base64.b64encode(json.dumps(payload).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    return f"header.{encoded_payload}.signature"


def test_is_token_expired_detects_expired_token():
    token = _jwt_with_payload(
        {"exp": (datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()}
    )

    assert is_token_expired(token) is True


def test_is_token_expired_accepts_future_token():
    token = _jwt_with_payload(
        {"exp": (datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp()}
    )

    assert is_token_expired(token) is False


def test_is_token_expired_treats_missing_exp_as_not_expired():
    token = _jwt_with_payload({})

    assert is_token_expired(token) is False


def test_euphrosyne_login_returns_access_and_refresh_tokens(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://euphrosyne.example/api/auth/long-token/",
        json={"access": "access-token", "refresh": "refresh-token"},
    )

    tokens = euphrosyne_login(
        "https://euphrosyne.example", "user@example.com", "secret"
    )

    assert tokens == ("access-token", "refresh-token")
    request = httpx_mock.get_request()
    assert json.loads(request.content) == {
        "email": "user@example.com",
        "password": "secret",
    }


def test_euphrosyne_login_returns_none_on_auth_failure(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://euphrosyne.example/api/auth/long-token/",
        status_code=401,
        json={"detail": "invalid credentials"},
    )

    assert (
        euphrosyne_login(
            "https://euphrosyne.example", "user@example.com", "bad-password"
        )
        is None
    )


def test_refresh_token_returns_new_access_token(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://euphrosyne.example/api/auth/token/refresh/",
        json={"access": "new-access-token"},
    )

    token = refresh_token("https://euphrosyne.example", "refresh-token")

    assert token == "new-access-token"
    request = httpx_mock.get_request()
    assert json.loads(request.content) == {"refresh": "refresh-token"}


def test_refresh_token_returns_none_on_refresh_failure(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://euphrosyne.example/api/auth/token/refresh/",
        status_code=401,
        json={"detail": "token_not_valid"},
    )

    assert refresh_token("https://euphrosyne.example", "expired-refresh-token") is None


def test_refresh_token_wraps_connection_errors(httpx_mock):
    httpx_mock.add_exception(
        httpx.ConnectError("connection failed"),
        method="POST",
        url="https://euphrosyne.example/api/auth/token/refresh/",
    )

    with pytest.raises(EuphrosyneConnectionError):
        refresh_token("https://euphrosyne.example", "refresh-token")


def test_auth_flow_refreshes_after_unauthorized_response():
    settings = FakeSettings()
    auth = EuphrosyneAuth(
        access_token="old-access-token",
        refresh_token="refresh-token",
        host="https://euphrosyne.example",
        settings=settings,
    )
    original_request = httpx.Request("GET", "https://tools.example/data")

    flow = auth.auth_flow(original_request)
    first_request = next(flow)
    first_authorization = first_request.headers["Authorization"]
    refresh_request = flow.send(httpx.Response(401, request=first_request))
    retry_request = flow.send(
        httpx.Response(
            200, json={"access": "new-access-token"}, request=refresh_request
        )
    )

    assert auth.access_token == "new-access-token"
    assert settings.values == {"access_token": "new-access-token"}
    assert first_authorization == "Bearer old-access-token"
    assert refresh_request.method == "POST"
    assert (
        str(refresh_request.url) == "https://euphrosyne.example/api/auth/token/refresh/"
    )
    assert retry_request.headers["Authorization"] == "Bearer new-access-token"


def test_update_tokens_stores_new_access_token():
    settings = FakeSettings()
    auth = EuphrosyneAuth(
        access_token="old-access-token",
        refresh_token="refresh-token",
        host="https://euphrosyne.example",
        settings=settings,
    )

    auth.update_tokens(httpx.Response(200, json={"access": "new-access-token"}))

    assert auth.access_token == "new-access-token"
    assert settings.values == {"access_token": "new-access-token"}
