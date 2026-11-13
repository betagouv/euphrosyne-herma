import base64
import binascii
import json
from datetime import datetime, timezone

import httpx
import keyring
import sentry_sdk
from PySide6.QtCore import QSettings

KEYRING_SERVICE = "Euphrosyne Herma"
KEYRING_REFRESH_TOKEN_ACCOUNT = "refresh_token"
HERMA_TOKEN_PATH = "/herma-token/"


class EuphrosyneConnectionError(Exception):
    """Custom exception for Euphrosyne connection errors."""

    def __init__(self):
        super().__init__(
            "Failed to connect to Euphrosyne server. Please check your connection and try again."
        )


class EuphrosyneAuthenticationError(Exception):
    """Raised when the user must authenticate again."""


class InvalidHermaTokenError(EuphrosyneAuthenticationError):
    """Raised when a pasted Herma token is malformed, expired or rejected."""


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


def get_herma_token_url(host: str) -> str:
    """Return the Euphrosyne page where users generate a Herma token."""
    return f"{host.rstrip('/')}{HERMA_TOKEN_PATH}"


def normalize_herma_token(raw_token: str) -> str:
    """
    Clean up a pasted Herma token and check it looks like a valid refresh token.

    Whitespace (including line breaks introduced when copying) and surrounding
    quotes are removed.

    Raises:
        InvalidHermaTokenError: If the token is malformed, not a refresh token
            or expired.
    """
    token = "".join((raw_token or "").split()).strip("\"'")
    if not token:
        raise InvalidHermaTokenError("Please paste a Herma token.")
    try:
        payload = decode_jwt_payload(token)
        expired = is_token_expired(token)
    except (ValueError, TypeError) as e:
        raise InvalidHermaTokenError(
            "This does not look like a Herma token. "
            "Copy the whole token generated on Euphrosyne and try again."
        ) from e
    token_type = payload.get("token_type")
    if token_type is not None and token_type != "refresh":
        raise InvalidHermaTokenError(
            "This token cannot be used to log in to Herma. "
            "Generate a Herma token on Euphrosyne and paste it."
        )
    if expired:
        raise InvalidHermaTokenError(
            "This Herma token has expired. Generate a new one on Euphrosyne."
        )
    return token


def login_with_herma_token(host: str, raw_token: str) -> tuple[str, str]:
    """
    Log in with a Herma token (a refresh token generated on Euphrosyne).

    Args:
        host (str): The base URL of the authentication server.
        raw_token (str): The token as pasted by the user.
    Returns:
        tuple[str, str]: The access token and the refresh token to store.
    Raises:
        InvalidHermaTokenError: If the token is malformed, expired or rejected.
        EuphrosyneConnectionError: If the server cannot be reached.
    """
    token = normalize_herma_token(raw_token)
    try:
        response = httpx.post(
            f"{host}/api/auth/token/refresh/",
            json={"refresh": token},
        )
    except httpx.HTTPError as e:
        raise EuphrosyneConnectionError() from e
    if response.status_code != 200:
        raise InvalidHermaTokenError(
            "Euphrosyne rejected this Herma token. It may be invalid, revoked "
            "or for another environment. Generate a new one and try again."
        )
    try:
        data = response.json()
    except ValueError as e:
        raise InvalidHermaTokenError(
            "Authentication server returned an invalid response."
        ) from e
    access_token = data.get("access") if isinstance(data, dict) else None
    if not isinstance(access_token, str) or not access_token:
        raise InvalidHermaTokenError(
            "Authentication server did not return an access token."
        )
    # Keep a rotated refresh token if the server returns one.
    new_refresh_token = data.get("refresh")
    if not isinstance(new_refresh_token, str) or not new_refresh_token:
        new_refresh_token = token
    return access_token, new_refresh_token


def refresh_token(host: str, refresh_token: str) -> tuple[str, str]:
    """
    Refresh the access token using the provided refresh token.

    Args:
        refresh_token (str): The refresh token to use for obtaining a new access token.

    Returns:
        tuple[str, str]: The new access and refresh tokens.

    Raises:
        ValueError: If the refresh fails.
    """
    try:
        response = httpx.post(
            f"{host}/api/auth/token/refresh/",
            json={"refresh": refresh_token},
        )
    except httpx.HTTPError as e:
        raise EuphrosyneConnectionError() from e
    if not response.status_code == 200:
        return None
    data = response.json()
    return data["access"]


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
            f"{self.host}/api/auth/token/refresh/",
            json={"refresh": self.refresh_token},
        )

    def update_tokens(self, response):
        # Update the `.access_token` and `.refresh_token` tokens
        # based on a refresh response.
        if response.status_code != 200:
            raise EuphrosyneAuthenticationError("Session expired. Please log in again.")

        try:
            data = response.json()
        except ValueError as e:
            raise EuphrosyneAuthenticationError(
                "Authentication server returned an invalid response."
            ) from e

        access_token = data.get("access")
        if not isinstance(access_token, str) or not access_token:
            raise EuphrosyneAuthenticationError(
                "Authentication server did not return an access token."
            )

        self.access_token = access_token
        self.settings.setValue("access_token", self.access_token)
