import pytest

from data_upload.app import login as login_module
from data_upload.config import resolve_config
from data_upload.euphrosyne.auth import (
    EuphrosyneConnectionError,
    InvalidHermaTokenError,
)

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


def _token_submission(environment="euphrosyne", token="pasted-token"):
    return {"environment": environment, "token": token}


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
    assert FakeLoginDialog.instances[1].kwargs == {
        "config": CONFIG,
        "selected_environment": "euphrosyne",
        "allow_environment_change": True,
    }
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
