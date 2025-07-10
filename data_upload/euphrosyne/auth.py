import base64
import json
from datetime import datetime, timezone

import httpx
from PySide6.QtCore import QSettings


class EuphrosyneConnectionError(Exception):
    """Custom exception for Euphrosyne connection errors."""

    def __init__(self):
        super().__init__(
            "Failed to connect to Euphrosyne server. Please check your connection and try again."
        )


def is_token_expired(token: str) -> bool:
    """
    Check if the provided JWT is valid.

    Args:
        token (str): The JWT to validate.

    Returns:
        bool: True if the JWT is valid, False otherwise.
    """
    decoded = base64.b64decode(token.split(".")[1] + "==").decode("utf-8")
    expiration = json.loads(decoded).get("exp")

    if not expiration:
        return False
    return expiration < datetime.now(timezone.utc).timestamp()


def euphrosyne_login(host: str, email: str, password: str) -> tuple[str, str]:
    """
    Log in a user and return a access & refresh token pair.
    Args:
        host (str): The base URL of the authentication server.
        email (str): The user's email.
        password (str): The user's password.
    Returns:
        tuple[str, str]: The access and refresh tokens if login is successful.
    Raises:
        ValueError: If the login fails.
    """
    response = httpx.post(
        f"{host}/api/auth/long-token/",
        json={"email": email, "password": password},
    )
    if not response.status_code == 200:
        return None
    data = response.json()
    return (data["access"], data["refresh"])


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
    except httpx.ConnectError as e:
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
        data = response.json()
        self.access_token = data["access"]
        self.settings.setValue("access_token", self.access_token)
