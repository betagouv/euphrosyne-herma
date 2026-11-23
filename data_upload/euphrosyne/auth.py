import base64
import binascii
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import keyring
import sentry_sdk
from PySide6.QtCore import QSettings

KEYRING_SERVICE = "Euphrosyne Herma"
KEYRING_REFRESH_TOKEN_ACCOUNT = "refresh_token"

# Herma signs in with Euphrosyne's OpenID Connect provider (OAuth 2.0 device
# authorization grant, RFC 8628), as the public client "herma".
HERMA_CLIENT_ID = "herma"
HERMA_SCOPE = "openid tools"
DEVICE_CODE_PATH = "/identity/o/api/device/code"
TOKEN_PATH = "/identity/o/api/token"
DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class EuphrosyneConnectionError(Exception):
    """Custom exception for Euphrosyne connection errors."""

    def __init__(self):
        super().__init__(
            "Failed to connect to Euphrosyne server. Please check your connection and try again."
        )


class EuphrosyneAuthenticationError(Exception):
    """Raised when the user must authenticate again."""


class DeviceAuthorizationError(EuphrosyneAuthenticationError):
    """The sign-in on Euphrosyne was denied, expired or failed."""


class AuthorizationPending(Exception):
    """The user has not approved the device on Euphrosyne yet."""

    def __init__(self, slow_down: bool = False):
        super().__init__("Waiting for approval on Euphrosyne.")
        # The server asks to poll less often.
        self.slow_down = slow_down


@dataclass(frozen=True)
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


def _capture_keyring_warning(operation: str, error: Exception):
    sentry_sdk.capture_message(
        f"Refresh token keyring {operation} failed: {type(error).__name__}",
        level="warning",
    )


def save_refresh_token(settings: QSettings, refresh_token: str):
    try:
        keyring.set_password(
            KEYRING_SERVICE,
            KEYRING_REFRESH_TOKEN_ACCOUNT,
            refresh_token,
        )
        settings.remove("refresh_token")
    except Exception as e:
        _capture_keyring_warning("save", e)
        settings.setValue("refresh_token", refresh_token)


def load_refresh_token(settings: QSettings) -> str | None:
    try:
        token = keyring.get_password(
            KEYRING_SERVICE,
            KEYRING_REFRESH_TOKEN_ACCOUNT,
        )
    except Exception as e:
        _capture_keyring_warning("load", e)
        return settings.value("refresh_token", None)

    return token or settings.value("refresh_token", None)


def clear_tokens(settings: QSettings):
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_REFRESH_TOKEN_ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception as e:
        _capture_keyring_warning("delete", e)
    settings.remove("access_token")
    settings.remove("refresh_token")


def decode_jwt_payload(token: str) -> dict:
    """
    Decode the payload of a JWT without verifying its signature.

    Raises:
        ValueError: If the token is not a well-formed JWT.
    """
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError("Token is not a JWT.")
    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_segment + padding)
        payload = json.loads(decoded.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise ValueError("Token payload cannot be decoded.") from error
    if not isinstance(payload, dict):
        raise ValueError("Token payload is not a JSON object.")
    return payload


def is_token_expired(token: str) -> bool:
    """
    Check whether the provided JWT is expired.

    Args:
        token (str): The JWT to check.

    Returns:
        bool: True if the JWT has an expiration date in the past, False otherwise.

    Raises:
        ValueError: If the token is not a well-formed JWT.
    """
    expiration = decode_jwt_payload(token).get("exp")

    if not expiration:
        return False
    return expiration < datetime.now(timezone.utc).timestamp()


def _post_form(url: str, data: dict) -> httpx.Response:
    try:
        return httpx.post(url, data=data)
    except httpx.HTTPError as e:
        raise EuphrosyneConnectionError() from e


def _json_object(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _tokens_from(data: dict, error: type[Exception]) -> tuple[str, str]:
    access_token = data.get("access_token")
    new_refresh_token = data.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        raise error("Authentication server did not return an access token.")
    if not isinstance(new_refresh_token, str) or not new_refresh_token:
        raise error("Authentication server did not return a refresh token.")
    return access_token, new_refresh_token


def start_device_authorization(host: str) -> DeviceAuthorization:
    """
    Ask Euphrosyne for a code that the user approves on its sign-in page.

    Raises:
        DeviceAuthorizationError: If Euphrosyne refuses the request.
        EuphrosyneConnectionError: If the server cannot be reached.
    """
    response = _post_form(
        f"{host.rstrip('/')}{DEVICE_CODE_PATH}",
        {"client_id": HERMA_CLIENT_ID, "scope": HERMA_SCOPE},
    )
    data = _json_object(response)
    try:
        if response.status_code != 200:
            raise ValueError(f"status {response.status_code}")
        return DeviceAuthorization(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            verification_uri_complete=data.get(
                "verification_uri_complete", data["verification_uri"]
            ),
            expires_in=int(data.get("expires_in", 300)),
            interval=int(data.get("interval", 5)),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise DeviceAuthorizationError(
            "Euphrosyne could not start the sign-in. Please try again later."
        ) from e


def poll_device_token(host: str, device_code: str) -> tuple[str, str]:
    """
    Ask Euphrosyne once whether the user approved the device.

    Returns:
        tuple[str, str]: The access token and the refresh token.

    Raises:
        AuthorizationPending: If the user has not answered yet.
        DeviceAuthorizationError: If the sign-in was denied or expired.
        EuphrosyneConnectionError: If the server cannot be reached.
    """
    response = _post_form(
        f"{host.rstrip('/')}{TOKEN_PATH}",
        {
            "grant_type": DEVICE_CODE_GRANT,
            "device_code": device_code,
            "client_id": HERMA_CLIENT_ID,
        },
    )
    data = _json_object(response)
    if response.status_code == 200:
        return _tokens_from(data, DeviceAuthorizationError)
    error = data.get("error")
    if error == "authorization_pending":
        raise AuthorizationPending()
    if error == "slow_down":
        raise AuthorizationPending(slow_down=True)
    if error == "access_denied":
        raise DeviceAuthorizationError("The sign-in was denied on Euphrosyne.")
    if error == "expired_token":
        raise DeviceAuthorizationError("The sign-in code expired. Please try again.")
    raise DeviceAuthorizationError("Euphrosyne refused the sign-in. Please try again.")


def wait_for_device_tokens(
    host: str,
    authorization: DeviceAuthorization,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, str]:
    """Poll Euphrosyne until the user approves or denies the device."""
    interval = authorization.interval
    deadline = time.monotonic() + authorization.expires_in
    while True:
        sleep(interval)
        try:
            return poll_device_token(host, authorization.device_code)
        except AuthorizationPending as pending:
            if pending.slow_down:
                interval += 5
        if time.monotonic() > deadline:
            raise DeviceAuthorizationError(
                "The sign-in code expired. Please try again."
            )


def refresh_tokens(host: str, refresh_token: str) -> tuple[str, str] | None:
    """
    Get a new access token with the refresh token.

    Euphrosyne rotates refresh tokens: the returned one replaces the given one,
    which no longer works.

    Returns:
        tuple[str, str] | None: The new access and refresh tokens, or None if
            the user must sign in again.

    Raises:
        EuphrosyneConnectionError: If the server cannot be reached.
    """
    response = _post_form(
        f"{host.rstrip('/')}{TOKEN_PATH}",
        _refresh_form(refresh_token),
    )
    if response.status_code != 200:
        return None
    try:
        return _tokens_from(_json_object(response), EuphrosyneAuthenticationError)
    except EuphrosyneAuthenticationError:
        return None


def _refresh_form(refresh_token: str) -> dict:
    return {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": HERMA_CLIENT_ID,
    }


class EuphrosyneAuth(httpx.Auth):
    requires_response_body = True

    def __init__(
        self, access_token: str, refresh_token: str, host: str, settings: QSettings
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.host = host
        self.settings = settings

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.access_token}"
        response = yield request

        if response.status_code == 401:
            # If the server issues a 401 response, then issue a request to
            # refresh tokens, and resend the request.
            refresh_response = yield self.build_refresh_request()
            self.update_tokens(refresh_response)

            request.headers["Authorization"] = f"Bearer {self.access_token}"
            yield request

    def build_refresh_request(self):
        # Return an `httpx.Request` for refreshing tokens.
        return httpx.Request(
            "POST",
            f"{self.host.rstrip('/')}{TOKEN_PATH}",
            data=_refresh_form(self.refresh_token),
        )

    def update_tokens(self, response):
        # Update the access and refresh tokens from a refresh response. The
        # refresh token is rotated: keep the new one, the old one is revoked.
        if response.status_code != 200:
            raise EuphrosyneAuthenticationError("Session expired. Please log in again.")

        try:
            data = response.json()
        except ValueError as e:
            raise EuphrosyneAuthenticationError(
                "Authentication server returned an invalid response."
            ) from e
        if not isinstance(data, dict):
            raise EuphrosyneAuthenticationError(
                "Authentication server returned an invalid response."
            )

        self.access_token, self.refresh_token = _tokens_from(
            data, EuphrosyneAuthenticationError
        )
        self.settings.setValue("access_token", self.access_token)
        save_refresh_token(self.settings, self.refresh_token)
