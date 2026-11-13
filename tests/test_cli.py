import base64
import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from data_upload import cli as cli_module
from data_upload.euphrosyne.auth import InvalidHermaTokenError


def _refresh_jwt() -> str:
    def encode(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    expiration = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    payload = {"token_type": "refresh", "exp": expiration}
    return f"{encode({'alg': 'HS256'})}.{encode(payload)}.signature"


class FakeSettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def value(self, key, default=None):
        return self.values.get(key, default)

    def remove(self, key):
        self.values.pop(key, None)


CONFIG_CATALOG = {
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


def test_cli_rejects_missing_data_path(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli_module.main(
            [
                "--project",
                "Project A",
                "--run",
                "Run 1",
                "--data-type",
                "raw-data",
            ]
        )

    assert exit_info.value.code == 2
    assert "--data-path" in capsys.readouterr().err


def test_cli_rejects_non_directory_data_path(tmp_path, capsys):
    exit_code = cli_module.main(
        [
            "--project",
            "Project A",
            "--run",
            "Run 1",
            "--data-type",
            "raw-data",
            "--data-path",
            str(tmp_path / "missing"),
        ]
    )

    assert exit_code == 1
    assert "Data path must be an existing directory" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("cli_data_type", "tools_data_type"),
    [
        ("raw-data", "raw_data"),
        ("processed-data", "processed_data"),
    ],
)
def test_cli_uploads_data_and_normalizes_data_type(
    monkeypatch, tmp_path, cli_data_type, tools_data_type
):
    data_path = tmp_path / "data"
    data_path.mkdir()
    settings = FakeSettings()
    calls = {
        "prompt": [],
        "login": [],
        "saved_refresh": [],
        "service": [],
        "init": [],
        "sas": [],
        "copy": [],
        "run": [],
    }

    class FakeToolsService:
        def __init__(self, host, auth):
            calls["service"].append((host, auth.access_token, auth.refresh_token))

        def init_folders(self, project_slug, run_name):
            calls["init"].append((project_slug, run_name))

        def get_run_data_upload_shared_access_signature(
            self, project_slug, run_name, data_type
        ):
            calls["sas"].append((project_slug, run_name, data_type))
            return {"url": "https://storage.example/share", "token": "sas-token"}

    def fake_login(host, raw_token):
        calls["login"].append((host, raw_token))
        return ("access-token", "refresh-token")

    def fake_save_refresh_token(saved_settings, refresh_token):
        calls["saved_refresh"].append((saved_settings, refresh_token))

    def fake_get_copy_command(src, dest, sas_token):
        calls["copy"].append((src, dest, sas_token))
        return ["azcopy", "copy"]

    def fake_run(command):
        calls["run"].append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli_module, "load_config", lambda: CONFIG_CATALOG)
    monkeypatch.setattr(cli_module, "QSettings", lambda org, app: settings)
    monkeypatch.setattr(
        "builtins.input", lambda prompt: pytest.fail("input should not be used")
    )
    monkeypatch.setattr(
        cli_module.getpass,
        "getpass",
        lambda prompt: calls["prompt"].append(prompt) or "pasted-token",
    )
    monkeypatch.setattr(cli_module, "login_with_herma_token", fake_login)
    monkeypatch.setattr(cli_module, "save_refresh_token", fake_save_refresh_token)
    monkeypatch.setattr(cli_module, "is_azcopy_installed", lambda: True)
    monkeypatch.setattr(
        cli_module,
        "download_azcopy",
        lambda: pytest.fail("download_azcopy should not be called"),
    )
    monkeypatch.setattr(cli_module, "EuphrosyneToolsService", FakeToolsService)
    monkeypatch.setattr(cli_module, "get_copy_command", fake_get_copy_command)
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)

    exit_code = cli_module.main(
        [
            "--project",
            "Project A",
            "--run",
            "Run 1",
            "--data-type",
            cli_data_type,
            "--data-path",
            str(data_path),
        ]
    )

    assert exit_code == 0
    assert settings.values == {"access_token": "access-token"}
    assert calls["prompt"] == ["Herma token: "]
    assert calls["login"] == [("https://euphrosyne.example", "pasted-token")]
    assert calls["saved_refresh"] == [(settings, "refresh-token")]
    assert calls["service"] == [
        ("https://tools.example", "access-token", "refresh-token")
    ]
    assert calls["init"] == [("Project A", "Run 1")]
    assert calls["sas"] == [("Project A", "Run 1", tools_data_type)]
    assert calls["copy"] == [
        (str(data_path), "https://storage.example/share", "sas-token")
    ]
    assert calls["run"] == [["azcopy", "copy"]]


def test_cli_accepts_environment_flag_and_uses_selected_hosts(monkeypatch, tmp_path):
    data_path = tmp_path / "data"
    data_path.mkdir()
    settings = FakeSettings()
    login_calls = []
    service_calls = []

    class FakeToolsService:
        def __init__(self, host, auth):
            service_calls.append((host, auth.host))

        def init_folders(self, project_name, run_name):
            pass

        def get_run_data_upload_shared_access_signature(
            self, project_slug, run_name, data_type
        ):
            return {"url": "https://storage.example/share", "token": "sas-token"}

    monkeypatch.setattr(cli_module, "load_config", lambda: CONFIG_CATALOG)
    monkeypatch.setattr(cli_module, "QSettings", lambda org, app: settings)
    monkeypatch.setattr(cli_module.getpass, "getpass", lambda prompt: "pasted-token")
    monkeypatch.setattr(
        cli_module,
        "login_with_herma_token",
        lambda host, raw_token: login_calls.append((host, raw_token))
        or ("access-token", "refresh-token"),
    )
    monkeypatch.setattr(cli_module, "save_refresh_token", lambda settings, token: None)
    monkeypatch.setattr(cli_module, "is_azcopy_installed", lambda: True)
    monkeypatch.setattr(cli_module, "EuphrosyneToolsService", FakeToolsService)
    monkeypatch.setattr(
        cli_module, "get_copy_command", lambda src, dest, token: ["azcopy"]
    )
    monkeypatch.setattr(
        cli_module.subprocess,
        "run",
        lambda command: subprocess.CompletedProcess(command, 0),
    )

    exit_code = cli_module.main(
        [
            "--project",
            "Project A",
            "--run",
            "Run 1",
            "--data-type",
            "raw-data",
            "--data-path",
            str(data_path),
            "--environment",
            "euphrosyne-staging",
        ]
    )

    assert exit_code == 0
    assert login_calls == [("https://staging.euphrosyne.example", "pasted-token")]
    assert service_calls == [
        ("https://staging.tools.example", "https://staging.euphrosyne.example")
    ]


def test_cli_rejects_unknown_environment(monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "load_config", lambda: CONFIG_CATALOG)

    with pytest.raises(SystemExit) as exit_info:
        cli_module.main(
            [
                "--project",
                "Project A",
                "--run",
                "Run 1",
                "--data-type",
                "raw-data",
                "--data-path",
                "/tmp",
                "--environment",
                "unknown",
            ]
        )

    assert exit_info.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


UPLOAD_ARGS = [
    "--project",
    "Project A",
    "--run",
    "Run 1",
    "--data-type",
    "raw-data",
]


def test_cli_prints_herma_token_page_before_prompting(monkeypatch, tmp_path, capsys):
    data_path = tmp_path / "data"
    data_path.mkdir()
    events = []

    def fake_getpass(prompt):
        events.append(("prompt", prompt, capsys.readouterr().err))
        return "pasted-token"

    def fake_login(host, raw_token):
        raise InvalidHermaTokenError("This Herma token has expired.")

    monkeypatch.setattr(cli_module, "load_config", lambda: CONFIG_CATALOG)
    monkeypatch.setattr(cli_module, "QSettings", lambda org, app: FakeSettings())
    monkeypatch.setattr(cli_module.getpass, "getpass", fake_getpass)
    monkeypatch.setattr(cli_module, "login_with_herma_token", fake_login)

    exit_code = cli_module.main(
        UPLOAD_ARGS
        + [
            "--data-path",
            str(data_path),
            "--environment",
            "euphrosyne-staging",
        ]
    )

    assert exit_code == 1
    assert len(events) == 1
    _, prompt, hint = events[0]
    assert prompt == "Herma token: "
    assert "https://staging.euphrosyne.example/herma-token/" in hint


def test_cli_returns_error_when_herma_token_is_invalid(monkeypatch, tmp_path, capsys):
    data_path = tmp_path / "data"
    data_path.mkdir()
    settings = FakeSettings()
    saved = []

    def fake_login(host, raw_token):
        raise InvalidHermaTokenError("Euphrosyne rejected this Herma token.")

    monkeypatch.setattr(cli_module, "load_config", lambda: CONFIG_CATALOG)
    monkeypatch.setattr(cli_module, "QSettings", lambda org, app: settings)
    monkeypatch.setattr(cli_module.getpass, "getpass", lambda prompt: "bad-token")
    monkeypatch.setattr(cli_module, "login_with_herma_token", fake_login)
    monkeypatch.setattr(
        cli_module, "save_refresh_token", lambda s, token: saved.append(token)
    )

    exit_code = cli_module.main(UPLOAD_ARGS + ["--data-path", str(data_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "Login failed" in err
    assert "Euphrosyne rejected this Herma token." in err
    assert "bad-token" not in err
    assert settings.values == {}
    assert saved == []


def test_cli_logs_in_with_herma_token(monkeypatch, tmp_path, httpx_mock):
    data_path = tmp_path / "data"
    data_path.mkdir()
    settings = FakeSettings()
    saved = []
    herma_token = _refresh_jwt()
    httpx_mock.add_response(
        method="POST",
        url="https://euphrosyne.example/api/auth/token/refresh/",
        json={"access": "access-token"},
    )

    class FakeToolsService:
        def __init__(self, host, auth):
            pass

        def init_folders(self, project_name, run_name):
            pass

        def get_run_data_upload_shared_access_signature(
            self, project_slug, run_name, data_type
        ):
            return {"url": "https://storage.example/share", "token": "sas-token"}

    monkeypatch.setattr(cli_module, "load_config", lambda: CONFIG_CATALOG)
    monkeypatch.setattr(cli_module, "QSettings", lambda org, app: settings)
    monkeypatch.setattr(cli_module.getpass, "getpass", lambda prompt: herma_token)
    monkeypatch.setattr(
        cli_module, "save_refresh_token", lambda s, token: saved.append(token)
    )
    monkeypatch.setattr(cli_module, "is_azcopy_installed", lambda: True)
    monkeypatch.setattr(cli_module, "EuphrosyneToolsService", FakeToolsService)
    monkeypatch.setattr(
        cli_module, "get_copy_command", lambda src, dest, token: ["azcopy"]
    )
    monkeypatch.setattr(
        cli_module.subprocess,
        "run",
        lambda command: subprocess.CompletedProcess(command, 0),
    )

    exit_code = cli_module.main(UPLOAD_ARGS + ["--data-path", str(data_path)])

    assert exit_code == 0
    requests = httpx_mock.get_requests()
    assert [str(request.url) for request in requests] == [
        "https://euphrosyne.example/api/auth/token/refresh/"
    ]
    assert json.loads(requests[0].content) == {"refresh": herma_token}
    assert settings.values == {"access_token": "access-token"}
    assert saved == [herma_token]


def test_cli_has_no_token_argument(monkeypatch):
    parser = cli_module.build_parser(CONFIG_CATALOG)
    options = {option for action in parser._actions for option in action.option_strings}
    assert not any("token" in option for option in options)
