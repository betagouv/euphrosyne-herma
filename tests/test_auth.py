import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from data_upload.euphrosyne.auth import (
    KEYRING_REFRESH_TOKEN_ACCOUNT,
    KEYRING_SERVICE,
    EuphrosyneAuth,
    EuphrosyneAuthenticationError,
    EuphrosyneConnectionError,
    InvalidHermaTokenError,
    clear_tokens,
    get_herma_token_url,
    is_token_expired,
    load_refresh_token,
    login_with_herma_token,
    normalize_herma_token,
    refresh_token,
    save_refresh_token,
)


class FakeSettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def value(self, key, default=None):
        return self.values.get(key, default)

    def remove(self, key):
        self.values.pop(key, None)


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


def test_is_token_expired_decodes_base64url_payload():
    payload = {
        "exp": (datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp(),
        "jti": "???>>>",
    }
    encoded_payload = (
        base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    assert "_" in encoded_payload or "-" in encoded_payload

    assert is_token_expired(f"header.{encoded_payload}.signature") is False


@pytest.mark.parametrize(
    "token",
    ["not-a-jwt", "header..signature", "header.!!!.signature", "a.b.c.d"],
)
def test_is_token_expired_rejects_malformed_token(token):
    with pytest.raises(ValueError):
        is_token_expired(token)


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("timeout"),
        httpx.RemoteProtocolError("protocol"),
        httpx.TooManyRedirects("redirects"),
    ],
)
def test_auth_network_calls_wrap_http_errors(httpx_mock, error):
    httpx_mock.add_exception(error, is_reusable=True)

    with pytest.raises(EuphrosyneConnectionError):
        refresh_token("https://euphrosyne.example", "refresh-token")
    with pytest.raises(EuphrosyneConnectionError):
        login_with_herma_token("https://euphrosyne.example", _refresh_jwt())


def test_get_herma_token_url():
    assert (
        get_herma_token_url("https://euphrosyne.example/")
        == "https://euphrosyne.example/herma-token/"
    )
    assert (
        get_herma_token_url("https://euphrosyne.example")
        == "https://euphrosyne.example/herma-token/"
    )


def _refresh_jwt(**overrides) -> str:
    payload = {
        "token_type": "refresh",
        "exp": (datetime.now(timezone.utc) + timedelta(days=30)).timestamp(),
        "jti": "abc",
        "user_id": 1,
    }
    payload.update(overrides)
    return _jwt_with_payload(payload)


def test_normalize_herma_token_trims_whitespace_and_quotes():
    token = _refresh_jwt()
    pasted = f'  "{token[:20]}\n{token[20:]}"\n'

    assert normalize_herma_token(pasted) == token


@pytest.mark.parametrize("raw", ["", "   ", "not-a-token", "a.b", "a.!!!.c"])
def test_normalize_herma_token_rejects_malformed_input(raw):
    with pytest.raises(InvalidHermaTokenError):
        normalize_herma_token(raw)


def test_normalize_herma_token_rejects_expired_token():
    token = _refresh_jwt(
        exp=(datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()
    )

    with pytest.raises(InvalidHermaTokenError, match="expired"):
        normalize_herma_token(token)


def test_normalize_herma_token_rejects_access_token():
    with pytest.raises(InvalidHermaTokenError):
        normalize_herma_token(_refresh_jwt(token_type="access"))


def test_login_with_herma_token_returns_access_and_pasted_refresh(httpx_mock):
    token = _refresh_jwt()
    httpx_mock.add_response(
        method="POST",
        url="https://euphrosyne.example/api/auth/token/refresh/",
        json={"access": "new-access-token"},
    )

    tokens = login_with_herma_token("https://euphrosyne.example", f" {token}\n")

    assert tokens == ("new-access-token", token)
    request = httpx_mock.get_request()
    assert json.loads(request.content) == {"refresh": token}


def test_login_with_herma_token_keeps_rotated_refresh_token(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://euphrosyne.example/api/auth/token/refresh/",
        json={"access": "new-access-token", "refresh": "rotated-refresh-token"},
    )

    assert login_with_herma_token("https://euphrosyne.example", _refresh_jwt()) == (
        "new-access-token",
        "rotated-refresh-token",
    )


def test_login_with_herma_token_does_not_call_server_for_invalid_token(httpx_mock):
    with pytest.raises(InvalidHermaTokenError):
        login_with_herma_token("https://euphrosyne.example", "garbage")

    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize(
    "response_kwargs",
    [
        {"status_code": 401, "json": {"detail": "Token is blacklisted"}},
        {"status_code": 400, "text": "bad request"},
        {"status_code": 500, "text": "oops"},
        {"status_code": 200, "text": "not json"},
        {"status_code": 200, "json": {"detail": "no access"}},
    ],
)
def test_login_with_herma_token_raises_on_rejected_token(httpx_mock, response_kwargs):
    httpx_mock.add_response(
        method="POST",
        url="https://euphrosyne.example/api/auth/token/refresh/",
        **response_kwargs,
    )

    with pytest.raises(InvalidHermaTokenError):
        login_with_herma_token("https://euphrosyne.example", _refresh_jwt())


def test_login_with_herma_token_wraps_connection_errors(httpx_mock):
    httpx_mock.add_exception(
        httpx.ConnectError("connection failed"),
        method="POST",
        url="https://euphrosyne.example/api/auth/token/refresh/",
    )

    with pytest.raises(EuphrosyneConnectionError):
        login_with_herma_token("https://euphrosyne.example", _refresh_jwt())


def test_herma_token_errors_never_contain_the_token(httpx_mock):
    token = _refresh_jwt(
        exp=(datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()
    )
    with pytest.raises(InvalidHermaTokenError) as error_info:
        login_with_herma_token("https://euphrosyne.example", token)
    assert token not in str(error_info.value)

    httpx_mock.add_response(
        method="POST",
        url="https://euphrosyne.example/api/auth/token/refresh/",
        status_code=401,
        json={"detail": "Token is invalid"},
    )
    valid_token = _refresh_jwt()
    with pytest.raises(InvalidHermaTokenError) as error_info:
        login_with_herma_token("https://euphrosyne.example", valid_token)
    assert valid_token not in str(error_info.value)


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


def test_auth_flow_raises_when_refresh_response_fails():
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
    refresh_request = flow.send(httpx.Response(401, request=first_request))

    with pytest.raises(EuphrosyneAuthenticationError, match="Session expired"):
        flow.send(
            httpx.Response(
                401, json={"detail": "token_not_valid"}, request=refresh_request
            )
        )

    assert auth.access_token == "old-access-token"
    assert settings.values == {}


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


@pytest.mark.parametrize(
    "response, message",
    [
        (
            httpx.Response(401, json={"detail": "token_not_valid"}),
            "Session expired",
        ),
        (
            httpx.Response(200, text="not json"),
            "invalid response",
        ),
        (
            httpx.Response(200, json={}),
            "did not return an access token",
        ),
        (
            httpx.Response(200, json={"access": None}),
            "did not return an access token",
        ),
    ],
)
def test_update_tokens_rejects_failed_or_malformed_refresh_responses(response, message):
    settings = FakeSettings()
    auth = EuphrosyneAuth(
        access_token="old-access-token",
        refresh_token="refresh-token",
        host="https://euphrosyne.example",
        settings=settings,
    )

    with pytest.raises(EuphrosyneAuthenticationError, match=message):
        auth.update_tokens(response)

    assert auth.access_token == "old-access-token"
    assert settings.values == {}


def test_clear_tokens_removes_access_and_refresh_tokens():
    settings = FakeSettings()
    settings.values = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "other": "kept",
    }

    clear_tokens(settings)

    assert settings.values == {"other": "kept"}


def test_save_refresh_token_uses_keyring_and_removes_legacy_settings_token(monkeypatch):
    settings = FakeSettings()
    settings.values = {"refresh_token": "legacy-refresh-token"}
    set_password_calls = []

    def fake_set_password(service, account, token):
        set_password_calls.append((service, account, token))

    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.keyring.set_password", fake_set_password
    )

    save_refresh_token(settings, "refresh-token")

    assert set_password_calls == [
        (KEYRING_SERVICE, KEYRING_REFRESH_TOKEN_ACCOUNT, "refresh-token")
    ]
    assert settings.values == {}


def test_save_refresh_token_falls_back_to_settings_and_warns_sentry(monkeypatch):
    settings = FakeSettings()
    sentry_calls = []

    def failing_set_password(service, account, token):
        raise RuntimeError("keyring unavailable")

    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.keyring.set_password", failing_set_password
    )
    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.sentry_sdk.capture_message",
        lambda *args, **kwargs: sentry_calls.append((args, kwargs)),
    )

    save_refresh_token(settings, "refresh-token")

    assert settings.values == {"refresh_token": "refresh-token"}
    assert sentry_calls == [
        (
            ("Refresh token keyring save failed: RuntimeError",),
            {"level": "warning"},
        )
    ]


def test_load_refresh_token_uses_keyring(monkeypatch):
    settings = FakeSettings()
    settings.values = {"refresh_token": "legacy-refresh-token"}

    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.keyring.get_password",
        lambda service, account: "keyring-refresh-token",
    )

    assert load_refresh_token(settings) == "keyring-refresh-token"


def test_load_refresh_token_falls_back_to_legacy_settings_without_warning_when_keyring_is_empty(
    monkeypatch,
):
    settings = FakeSettings()
    settings.values = {"refresh_token": "legacy-refresh-token"}
    sentry_calls = []

    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.keyring.get_password",
        lambda service, account: None,
    )
    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.sentry_sdk.capture_message",
        lambda *args, **kwargs: sentry_calls.append((args, kwargs)),
    )

    assert load_refresh_token(settings) == "legacy-refresh-token"
    assert sentry_calls == []


def test_load_refresh_token_falls_back_to_settings_and_warns_sentry(monkeypatch):
    settings = FakeSettings()
    settings.values = {"refresh_token": "legacy-refresh-token"}
    sentry_calls = []

    def failing_get_password(service, account):
        raise RuntimeError("keyring unavailable")

    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.keyring.get_password", failing_get_password
    )
    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.sentry_sdk.capture_message",
        lambda *args, **kwargs: sentry_calls.append((args, kwargs)),
    )

    assert load_refresh_token(settings) == "legacy-refresh-token"
    assert sentry_calls == [
        (
            ("Refresh token keyring load failed: RuntimeError",),
            {"level": "warning"},
        )
    ]


def test_clear_tokens_deletes_keyring_token_and_settings_tokens(monkeypatch):
    settings = FakeSettings()
    settings.values = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "other": "kept",
    }
    delete_calls = []

    def fake_delete_password(service, account):
        delete_calls.append((service, account))

    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.keyring.delete_password",
        fake_delete_password,
    )

    clear_tokens(settings)

    assert delete_calls == [(KEYRING_SERVICE, KEYRING_REFRESH_TOKEN_ACCOUNT)]
    assert settings.values == {"other": "kept"}


def test_clear_tokens_removes_settings_tokens_and_warns_when_keyring_delete_fails(
    monkeypatch,
):
    settings = FakeSettings()
    settings.values = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "other": "kept",
    }
    sentry_calls = []

    def failing_delete_password(service, account):
        raise RuntimeError("keyring unavailable")

    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.keyring.delete_password",
        failing_delete_password,
    )
    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.sentry_sdk.capture_message",
        lambda *args, **kwargs: sentry_calls.append((args, kwargs)),
    )

    clear_tokens(settings)

    assert settings.values == {"other": "kept"}
    assert sentry_calls == [
        (
            ("Refresh token keyring delete failed: RuntimeError",),
            {"level": "warning"},
        )
    ]
