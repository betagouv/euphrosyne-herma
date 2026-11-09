import pytest

from data_upload.app import login as login_module
from data_upload.config import resolve_config
from data_upload.euphrosyne.auth import (
    EuphrosyneConnectionError,
    EuphrosyneTokenLoginRequiredError,
    InvalidHermaTokenError,
)
from data_upload.widget.login import LOGIN_MODE_PASSWORD, LOGIN_MODE_TOKEN

CONFIG = {
    "default-environment": "euphrosyne",
    "environments": {
        "euphrosyne": {
            "url": "https://euphrosyne.example",
            "euphro-tools-url": "https://tools.example",
        },
        "euphrosyne-staging": {
            "url": "https://staging.euphrosyne.example",
            "euphro-tools-url": "https://staging.tools.example",
        },
    },
}


class FakeSettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def value(self, key, default=None):
        return self.values.get(key, default)

    def remove(self, key):
        self.values.pop(key, None)


class FakeLoginDialog:
    """Replays scripted dialog submissions and records constructor arguments."""

    submissions: list = []
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.submission = self.submissions.pop(0)
        FakeLoginDialog.instances.append(self)

    def exec(self):
        return self.submission is not None

    def get_login_mode(self):
        return self.submission["mode"]

    def get_login_data(self):
        return (
            self.submission["environment"],
            self.submission["email"],
            self.submission["password"],
        )

    def get_token_login_data(self):
        return self.submission["environment"], self.submission["token"]


class FakeMessageBox:
    messages: list = []

    @classmethod
    def critical(cls, parent, title, message):
        cls.messages.append((title, message))


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.delenv("EUPHROSYNE_URL", raising=False)
    FakeLoginDialog.submissions = []
    FakeLoginDialog.instances = []
    FakeMessageBox.messages = []
    saved_refresh_tokens = []
    monkeypatch.setattr(login_module, "LoginDialog", FakeLoginDialog)
    monkeypatch.setattr(login_module, "QMessageBox", FakeMessageBox)
    monkeypatch.setattr(
        login_module,
        "save_refresh_token",
        lambda settings, token: saved_refresh_tokens.append(token),
    )
    return saved_refresh_tokens


def _password_submission(environment="euphrosyne", email="user@example.com"):
    return {
        "mode": LOGIN_MODE_PASSWORD,
        "environment": environment,
        "email": email,
        "password": "secret",
    }


def _token_submission(environment="euphrosyne", token="pasted-token"):
    return {"mode": LOGIN_MODE_TOKEN, "environment": environment, "token": token}


def test_login_user_with_password_stores_tokens(monkeypatch, fakes):
    FakeLoginDialog.submissions = [_password_submission()]
    monkeypatch.setattr(
        login_module,
        "euphrosyne_login",
        lambda host, email, password: ("access", "refresh"),
    )
    settings = FakeSettings()

    config = login_module.login_user(
        CONFIG, resolve_config(CONFIG, "euphrosyne"), settings
    )

    assert config["environment"] == "euphrosyne"
    assert settings.values == {"access_token": "access", "environment": "euphrosyne"}
    assert fakes == ["refresh"]


def test_login_user_with_herma_token_stores_tokens(monkeypatch, fakes):
    FakeLoginDialog.submissions = [_token_submission(environment="euphrosyne-staging")]
    calls = []

    def fake_login_with_herma_token(host, raw_token):
        calls.append((host, raw_token))
        return "access", "pasted-token"

    monkeypatch.setattr(
        login_module, "login_with_herma_token", fake_login_with_herma_token
    )
    settings = FakeSettings()

    config = login_module.login_user(
        CONFIG, resolve_config(CONFIG, "euphrosyne"), settings
    )

    assert calls == [("https://staging.euphrosyne.example", "pasted-token")]
    assert config["environment"] == "euphrosyne-staging"
    assert settings.values == {
        "access_token": "access",
        "environment": "euphrosyne-staging",
    }
    assert fakes == ["pasted-token"]
    assert FakeMessageBox.messages == []


def test_login_user_switches_to_token_mode_when_password_login_is_refused(
    monkeypatch, fakes
):
    FakeLoginDialog.submissions = [
        _password_submission(environment="euphrosyne-staging"),
        _token_submission(environment="euphrosyne-staging"),
    ]

    def refuse_password_login(host, email, password):
        raise EuphrosyneTokenLoginRequiredError()

    monkeypatch.setattr(login_module, "euphrosyne_login", refuse_password_login)
    monkeypatch.setattr(
        login_module,
        "login_with_herma_token",
        lambda host, raw_token: ("access", raw_token),
    )
    settings = FakeSettings()

    login_module.login_user(CONFIG, resolve_config(CONFIG, "euphrosyne"), settings)

    assert [title for title, _ in FakeMessageBox.messages] == ["Herma token required"]
    assert "Paste a Herma token" in FakeMessageBox.messages[0][1]
    second_dialog = FakeLoginDialog.instances[1]
    assert second_dialog.kwargs["login_mode"] == LOGIN_MODE_TOKEN
    assert second_dialog.kwargs["selected_environment"] == "euphrosyne-staging"
    assert second_dialog.kwargs["email"] == "user@example.com"
    assert fakes == ["pasted-token"]


def test_login_user_retries_after_invalid_token(monkeypatch, fakes):
    FakeLoginDialog.submissions = [
        _token_submission(token="bad-token"),
        _token_submission(token="good-token"),
    ]

    def fake_login_with_herma_token(host, raw_token):
        if raw_token == "bad-token":
            raise InvalidHermaTokenError("This Herma token has expired.")
        return "access", raw_token

    monkeypatch.setattr(
        login_module, "login_with_herma_token", fake_login_with_herma_token
    )
    settings = FakeSettings()

    login_module.login_user(CONFIG, resolve_config(CONFIG, "euphrosyne"), settings)

    assert FakeMessageBox.messages == [
        ("Invalid Herma token", "This Herma token has expired.")
    ]
    assert FakeLoginDialog.instances[1].kwargs["login_mode"] == LOGIN_MODE_TOKEN
    assert fakes == ["good-token"]


def test_login_user_reports_connection_errors(monkeypatch, fakes):
    FakeLoginDialog.submissions = [_token_submission(), None]

    def fail(host, raw_token):
        raise EuphrosyneConnectionError()

    monkeypatch.setattr(login_module, "login_with_herma_token", fail)

    with pytest.raises(SystemExit) as exit_info:
        login_module.login_user(
            CONFIG, resolve_config(CONFIG, "euphrosyne"), FakeSettings()
        )

    assert exit_info.value.code == 0
    assert [title for title, _ in FakeMessageBox.messages] == ["Connection Error"]
    assert fakes == []


def test_login_user_reports_generic_password_failure(monkeypatch, fakes):
    FakeLoginDialog.submissions = [_password_submission(), None]
    monkeypatch.setattr(
        login_module, "euphrosyne_login", lambda host, email, password: None
    )

    with pytest.raises(SystemExit):
        login_module.login_user(
            CONFIG, resolve_config(CONFIG, "euphrosyne"), FakeSettings()
        )

    assert FakeMessageBox.messages == [
        ("Login Failed", "Failed to log in. Please check your credentials.")
    ]
    assert FakeLoginDialog.instances[1].kwargs["login_mode"] == LOGIN_MODE_PASSWORD
    assert fakes == []


def test_login_user_keeps_environment_locked_during_relogin(monkeypatch, fakes):
    FakeLoginDialog.submissions = [_token_submission(environment="euphrosyne-staging")]
    monkeypatch.setattr(
        login_module,
        "login_with_herma_token",
        lambda host, raw_token: ("access", raw_token),
    )

    login_module.login_user(
        CONFIG,
        resolve_config(CONFIG, "euphrosyne-staging"),
        FakeSettings(),
        allow_environment_change=False,
    )

    assert FakeLoginDialog.instances[0].kwargs["allow_environment_change"] is False
