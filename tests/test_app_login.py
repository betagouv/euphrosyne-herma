import pytest

from data_upload.app import login as login_module
from data_upload.config import resolve_config

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
    """Replays a scripted sign-in result and records constructor arguments."""

    results: list = []
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.result = self.results.pop(0)
        FakeLoginDialog.instances.append(self)

    def exec(self):
        return self.result is not None

    def get_login_result(self):
        return self.result


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.delenv("EUPHROSYNE_URL", raising=False)
    FakeLoginDialog.results = []
    FakeLoginDialog.instances = []
    saved_refresh_tokens = []
    monkeypatch.setattr(login_module, "LoginDialog", FakeLoginDialog)
    monkeypatch.setattr(
        login_module,
        "save_refresh_token",
        lambda settings, token: saved_refresh_tokens.append(token),
    )
    return saved_refresh_tokens


def test_login_user_stores_tokens_of_the_signed_in_environment(fakes):
    FakeLoginDialog.results = [("euphrosyne-staging", "access", "refresh")]
    settings = FakeSettings()

    config = login_module.login_user(
        CONFIG, resolve_config(CONFIG, "euphrosyne"), settings
    )

    assert config["environment"] == "euphrosyne-staging"
    assert settings.values == {
        "access_token": "access",
        "environment": "euphrosyne-staging",
    }
    assert fakes == ["refresh"]
    assert FakeLoginDialog.instances[0].kwargs == {
        "config": CONFIG,
        "selected_environment": "euphrosyne",
        "allow_environment_change": True,
    }


def test_login_user_exits_when_the_dialog_is_cancelled(fakes):
    FakeLoginDialog.results = [None]

    with pytest.raises(SystemExit) as exit_info:
        login_module.login_user(
            CONFIG, resolve_config(CONFIG, "euphrosyne"), FakeSettings()
        )

    assert exit_info.value.code == 0
    assert fakes == []


def test_login_user_keeps_environment_locked_during_relogin(fakes):
    FakeLoginDialog.results = [("euphrosyne-staging", "access", "refresh")]

    login_module.login_user(
        CONFIG,
        resolve_config(CONFIG, "euphrosyne-staging"),
        FakeSettings(),
        allow_environment_change=False,
    )

    assert FakeLoginDialog.instances[0].kwargs["allow_environment_change"] is False
