import subprocess

import pytest

from data_upload import cli as cli_module


class FakeSettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def value(self, key, default=None):
        return self.values.get(key, default)

    def remove(self, key):
        self.values.pop(key, None)


CONFIG = {
    "euphrosyne": {"url": "https://euphrosyne.example"},
    "euphrosyne-tools": {"url": "https://tools.example"},
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
        "input": [],
        "password": [],
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

    def fake_login(host, email, password):
        calls["login"].append((host, email, password))
        return ("access-token", "refresh-token")

    def fake_save_refresh_token(saved_settings, refresh_token):
        calls["saved_refresh"].append((saved_settings, refresh_token))

    def fake_get_copy_command(src, dest, sas_token):
        calls["copy"].append((src, dest, sas_token))
        return ["azcopy", "copy"]

    def fake_run(command):
        calls["run"].append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli_module, "load_config", lambda: CONFIG)
    monkeypatch.setattr(cli_module, "QSettings", lambda org, app: settings)
    monkeypatch.setattr("builtins.input", lambda prompt: "user@example.com")
    monkeypatch.setattr(
        cli_module.getpass,
        "getpass",
        lambda prompt: calls["password"].append(prompt) or "secret",
    )
    monkeypatch.setattr(cli_module, "euphrosyne_login", fake_login)
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
    assert calls["password"] == ["Password: "]
    assert calls["login"] == [
        ("https://euphrosyne.example", "user@example.com", "secret")
    ]
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


def test_cli_uses_provided_email_without_prompting(monkeypatch, tmp_path):
    data_path = tmp_path / "data"
    data_path.mkdir()
    settings = FakeSettings()
    login_calls = []

    class FakeToolsService:
        def __init__(self, host, auth):
            pass

        def init_folders(self, project_name, run_name):
            pass

        def get_run_data_upload_shared_access_signature(
            self, project_slug, run_name, data_type
        ):
            return {"url": "https://storage.example/share", "token": "sas-token"}

    monkeypatch.setattr(cli_module, "load_config", lambda: CONFIG)
    monkeypatch.setattr(cli_module, "QSettings", lambda org, app: settings)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: pytest.fail("email should not be prompted"),
    )
    monkeypatch.setattr(cli_module.getpass, "getpass", lambda prompt: "secret")
    monkeypatch.setattr(
        cli_module,
        "euphrosyne_login",
        lambda host, email, password: login_calls.append((host, email, password))
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
            "--email",
            "provided@example.com",
        ]
    )

    assert exit_code == 0
    assert login_calls == [
        ("https://euphrosyne.example", "provided@example.com", "secret")
    ]


def test_cli_returns_error_when_login_fails(monkeypatch, tmp_path, capsys):
    data_path = tmp_path / "data"
    data_path.mkdir()
    monkeypatch.setattr(cli_module, "load_config", lambda: CONFIG)
    monkeypatch.setattr(cli_module, "QSettings", lambda org, app: FakeSettings())
    monkeypatch.setattr("builtins.input", lambda prompt: "user@example.com")
    monkeypatch.setattr(cli_module.getpass, "getpass", lambda prompt: "secret")
    monkeypatch.setattr(
        cli_module, "euphrosyne_login", lambda host, email, password: None
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
        ]
    )

    assert exit_code == 1
    assert "Login failed" in capsys.readouterr().err
