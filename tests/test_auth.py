import base64
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import httpx
import pytest

from data_upload.euphrosyne.auth import (
    KEYRING_REFRESH_TOKEN_ACCOUNT,
    KEYRING_SERVICE,
    AuthorizationPending,
    DeviceAuthorization,
    DeviceAuthorizationError,
    EuphrosyneAuth,
    EuphrosyneAuthenticationError,
    EuphrosyneConnectionError,
    clear_tokens,
    is_token_expired,
    load_refresh_token,
    poll_device_token,
    refresh_tokens,
    save_refresh_token,
    start_device_authorization,
    wait_for_device_tokens,
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


HOST = "https://euphrosyne.example"
TOKEN_URL = f"{HOST}/identity/o/api/token"
DEVICE_CODE_URL = f"{HOST}/identity/o/api/device/code"
DEVICE_RESPONSE = {
    "device_code": "device-code",
    "user_code": "ABCD-EFGH",
    "verification_uri": f"{HOST}/identity/o/device",
    "verification_uri_complete": f"{HOST}/identity/o/device?code=ABCD-EFGH",
    "expires_in": 300,
    "interval": 5,
}
TOKEN_RESPONSE = {
    "access_token": "access-token",
    "refresh_token": "new-refresh-token",
    "token_type": "Bearer",
    "expires_in": 300,
}


def _form(request: httpx.Request) -> dict:
    return dict(parse_qsl(request.content.decode()))


@pytest.fixture(name="saved_refresh_tokens")
def saved_refresh_tokens_fixture(monkeypatch):
    saved = []
    monkeypatch.setattr(
        "data_upload.euphrosyne.auth.save_refresh_token",
        lambda settings, token: saved.append(token),
    )
    return saved


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
        refresh_tokens(HOST, "refresh-token")
    with pytest.raises(EuphrosyneConnectionError):
        start_device_authorization(HOST)
    with pytest.raises(EuphrosyneConnectionError):
        poll_device_token(HOST, "device-code")


def test_start_device_authorization_asks_for_a_herma_code(httpx_mock):
    httpx_mock.add_response(method="POST", url=DEVICE_CODE_URL, json=DEVICE_RESPONSE)

    authorization = start_device_authorization(f"{HOST}/")

    assert authorization == DeviceAuthorization(
        device_code="device-code",
        user_code="ABCD-EFGH",
        verification_uri=f"{HOST}/identity/o/device",
        verification_uri_complete=f"{HOST}/identity/o/device?code=ABCD-EFGH",
        expires_in=300,
        interval=5,
    )
    assert _form(httpx_mock.get_request()) == {
        "client_id": "herma",
        "scope": "openid tools",
    }


@pytest.mark.parametrize(
    "response_kwargs",
    [
        {"status_code": 400, "json": {"error": "invalid_client"}},
        {"status_code": 200, "json": {"user_code": "ABCD"}},
        {"status_code": 200, "text": "not json"},
    ],
)
def test_start_device_authorization_raises_when_refused(httpx_mock, response_kwargs):
    httpx_mock.add_response(method="POST", url=DEVICE_CODE_URL, **response_kwargs)

    with pytest.raises(DeviceAuthorizationError):
        start_device_authorization(HOST)


def test_poll_device_token_returns_tokens_once_approved(httpx_mock):
    httpx_mock.add_response(method="POST", url=TOKEN_URL, json=TOKEN_RESPONSE)

    assert poll_device_token(HOST, "device-code") == (
        "access-token",
        "new-refresh-token",
    )
    assert _form(httpx_mock.get_request()) == {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": "device-code",
        "client_id": "herma",
    }


@pytest.mark.parametrize(
    "error, slow_down", [("authorization_pending", False), ("slow_down", True)]
)
def test_poll_device_token_raises_pending(httpx_mock, error, slow_down):
    httpx_mock.add_response(
        method="POST", url=TOKEN_URL, status_code=400, json={"error": error}
    )

    with pytest.raises(AuthorizationPending) as pending:
        poll_device_token(HOST, "device-code")

    assert pending.value.slow_down is slow_down


@pytest.mark.parametrize(
    "response_kwargs, message",
    [
        ({"status_code": 400, "json": {"error": "access_denied"}}, "denied"),
        ({"status_code": 400, "json": {"error": "expired_token"}}, "expired"),
        ({"status_code": 400, "json": {"error": "invalid_client"}}, "refused"),
        ({"status_code": 500, "text": "error"}, "refused"),
        ({"status_code": 200, "json": {"access_token": "a"}}, "refresh token"),
    ],
)
def test_poll_device_token_raises_on_failure(httpx_mock, response_kwargs, message):
    httpx_mock.add_response(method="POST", url=TOKEN_URL, **response_kwargs)

    with pytest.raises(DeviceAuthorizationError, match=message):
        poll_device_token(HOST, "device-code")


def test_wait_for_device_tokens_polls_until_approved(httpx_mock):
    for error in ("authorization_pending", "slow_down"):
        httpx_mock.add_response(
            method="POST", url=TOKEN_URL, status_code=400, json={"error": error}
        )
    httpx_mock.add_response(method="POST", url=TOKEN_URL, json=TOKEN_RESPONSE)
    sleeps = []

    tokens = wait_for_device_tokens(
        HOST,
        DeviceAuthorization(**DEVICE_RESPONSE),
        sleep=sleeps.append,
    )

    assert tokens == ("access-token", "new-refresh-token")
    # The interval grows by five seconds after "slow_down".
    assert sleeps == [5, 5, 10]


def test_wait_for_device_tokens_stops_when_denied(httpx_mock):
    httpx_mock.add_response(
        method="POST", url=TOKEN_URL, status_code=400, json={"error": "access_denied"}
    )

    with pytest.raises(DeviceAuthorizationError, match="denied"):
        wait_for_device_tokens(
            HOST, DeviceAuthorization(**DEVICE_RESPONSE), sleep=lambda _: None
        )


def test_refresh_tokens_returns_rotated_tokens(httpx_mock):
    httpx_mock.add_response(method="POST", url=TOKEN_URL, json=TOKEN_RESPONSE)

    assert refresh_tokens(HOST, "refresh-token") == (
        "access-token",
        "new-refresh-token",
    )
    assert _form(httpx_mock.get_request()) == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-token",
        "client_id": "herma",
    }


@pytest.mark.parametrize(
    "response_kwargs",
    [
        {"status_code": 400, "json": {"error": "invalid_grant"}},
        {"status_code": 200, "json": {"access_token": "access-token"}},
        {"status_code": 200, "text": "not json"},
    ],
)
def test_refresh_tokens_returns_none_when_sign_in_is_needed(
    httpx_mock, response_kwargs
):
    httpx_mock.add_response(method="POST", url=TOKEN_URL, **response_kwargs)

    assert refresh_tokens(HOST, "expired-refresh-token") is None


def test_auth_flow_refreshes_after_unauthorized_response(saved_refresh_tokens):
    settings = FakeSettings()
    auth = EuphrosyneAuth(
        access_token="old-access-token",
        refresh_token="refresh-token",
        host=HOST,
        settings=settings,
    )
    original_request = httpx.Request("GET", "https://tools.example/data")

    flow = auth.auth_flow(original_request)
    first_request = next(flow)
    first_authorization = first_request.headers["Authorization"]
    refresh_request = flow.send(httpx.Response(401, request=first_request))
    retry_request = flow.send(
        httpx.Response(200, json=TOKEN_RESPONSE, request=refresh_request)
    )

    assert first_authorization == "Bearer old-access-token"
    assert refresh_request.method == "POST"
    assert str(refresh_request.url) == TOKEN_URL
    assert _form(refresh_request) == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-token",
        "client_id": "herma",
    }
    assert retry_request.headers["Authorization"] == "Bearer access-token"
    # The refresh token is rotated: the new one is kept for the next refresh.
    assert auth.refresh_token == "new-refresh-token"
    assert settings.values == {"access_token": "access-token"}
    assert saved_refresh_tokens == ["new-refresh-token"]


def test_auth_flow_raises_when_refresh_response_fails(saved_refresh_tokens):
    settings = FakeSettings()
    auth = EuphrosyneAuth(
        access_token="old-access-token",
        refresh_token="refresh-token",
        host=HOST,
        settings=settings,
    )
    original_request = httpx.Request("GET", "https://tools.example/data")

    flow = auth.auth_flow(original_request)
    first_request = next(flow)
    refresh_request = flow.send(httpx.Response(401, request=first_request))

    with pytest.raises(EuphrosyneAuthenticationError, match="Session expired"):
        flow.send(
            httpx.Response(
                400, json={"error": "invalid_grant"}, request=refresh_request
            )
        )

    assert auth.access_token == "old-access-token"
    assert settings.values == {}
    assert saved_refresh_tokens == []


@pytest.mark.parametrize(
    "response, message",
    [
        (httpx.Response(400, json={"error": "invalid_grant"}), "Session expired"),
        (httpx.Response(200, text="not json"), "invalid response"),
        (httpx.Response(200, json=[]), "invalid response"),
        (httpx.Response(200, json={}), "did not return an access token"),
        (
            httpx.Response(200, json={"access_token": "access-token"}),
            "did not return a refresh token",
        ),
    ],
)
def test_update_tokens_rejects_failed_or_malformed_refresh_responses(
    response, message, saved_refresh_tokens
):
    settings = FakeSettings()
    auth = EuphrosyneAuth(
        access_token="old-access-token",
        refresh_token="refresh-token",
        host=HOST,
        settings=settings,
    )

    with pytest.raises(EuphrosyneAuthenticationError, match=message):
        auth.update_tokens(response)

    assert auth.access_token == "old-access-token"
    assert settings.values == {}
    assert saved_refresh_tokens == []


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
