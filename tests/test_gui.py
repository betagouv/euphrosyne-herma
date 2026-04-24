import sys

import httpx
import pytest

from data_upload import gui as gui_module
from data_upload.euphrosyne.project import ProjectLoadingError

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

DEFAULT_CONFIG = {
    "environment": "euphrosyne",
    "euphrosyne": {"url": "https://euphrosyne.example"},
    "euphrosyne-tools": {"url": "https://tools.example"},
}

STAGING_CONFIG = {
    "environment": "euphrosyne-staging",
    "euphrosyne": {"url": "https://staging.euphrosyne.example"},
    "euphrosyne-tools": {"url": "https://staging.tools.example"},
}


class FakeMessageBox:
    critical_calls = []
    warning_calls = []

    @classmethod
    def critical(cls, *args):
        cls.critical_calls.append(args)

    @classmethod
    def warning(cls, *args):
        cls.warning_calls.append(args)


class FakeStartupDialog:
    instances = []

    def __init__(self, app):
        self.app = app
        self.messages = []
        self.close_count = 0
        FakeStartupDialog.instances.append(self)

    def show_message(self, message):
        self.messages.append(message)

    def close(self):
        self.close_count += 1


class FakeDataUploadWidget:
    instances = []

    def __init__(self, config_catalog, config, settings, stdout_stream=None):
        self.config_catalog = config_catalog
        self.config = config
        self.settings = settings
        self.stdout_stream = stdout_stream
        self.window_title = None
        self.show_count = 0
        FakeDataUploadWidget.instances.append(self)

    def setWindowTitle(self, title):
        self.window_title = title

    def show(self):
        self.show_count += 1


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def _patch_startup_dependencies(
    monkeypatch,
    projects_or_error,
    login_required=False,
    settings=None,
):
    FakeMessageBox.critical_calls = []
    FakeMessageBox.warning_calls = []
    FakeStartupDialog.instances = []
    FakeDataUploadWidget.instances = []
    settings = settings or FakeSettings()
    monkeypatch.setattr(sys, "argv", ["euphrosyne-herma"])
    monkeypatch.setattr(gui_module, "settings", settings)
    monkeypatch.setattr(gui_module, "QMessageBox", FakeMessageBox)
    monkeypatch.setattr(gui_module, "StartupDialog", FakeStartupDialog)
    monkeypatch.setattr(gui_module, "load_config", lambda: CONFIG_CATALOG)
    monkeypatch.setattr(gui_module, "init_azcopy", lambda app: None)
    monkeypatch.setattr(
        gui_module,
        "init_access_token",
        lambda settings, config: login_required,
    )
    monkeypatch.setattr(
        gui_module,
        "login_user",
        lambda config_catalog, config, settings: config,
    )
    monkeypatch.setattr(gui_module, "DataUploadWidget", FakeDataUploadWidget)

    def fake_list_projects(host, access_token):
        if isinstance(projects_or_error, Exception):
            raise projects_or_error
        return projects_or_error

    monkeypatch.setattr(gui_module, "list_projects", fake_list_projects)


def test_startup_dialog_is_modeless_and_has_no_message_box_buttons(qapp):
    startup_dialog = gui_module.StartupDialog(qapp)

    startup_dialog.show_message("Checking AzCopy...")

    assert startup_dialog.dialog.isModal() is False
    assert startup_dialog.label.text() == "Checking AzCopy..."
    assert startup_dialog.progress_bar.minimum() == 0
    assert startup_dialog.progress_bar.maximum() == 0

    startup_dialog.close()


def test_startup_feedback_is_shown_and_updated_before_main_window(qapp, monkeypatch):
    _patch_startup_dependencies(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    monkeypatch.setattr(qapp, "exec", lambda: 0)

    with pytest.raises(SystemExit) as exit_info:
        gui_module.ConverterGUI.start()

    assert exit_info.value.code == 0
    assert FakeStartupDialog.instances[0].messages == [
        "Loading configuration...",
        "Checking AzCopy...",
        "Checking authentication...",
        "Loading projects...",
        "Opening upload window...",
    ]
    assert FakeStartupDialog.instances[0].close_count == 1
    assert FakeDataUploadWidget.instances[0].show_count == 1
    assert FakeDataUploadWidget.instances[0].config == DEFAULT_CONFIG


def test_startup_feedback_closes_before_login_and_reopens_after_success(
    qapp, monkeypatch
):
    login_calls = []
    _patch_startup_dependencies(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
        login_required=True,
    )
    monkeypatch.setattr(
        gui_module,
        "login_user",
        lambda config_catalog, config, settings: login_calls.append(
            (config_catalog, config, settings)
        )
        or config,
    )
    monkeypatch.setattr(qapp, "exec", lambda: 0)

    with pytest.raises(SystemExit) as exit_info:
        gui_module.ConverterGUI.start()

    assert exit_info.value.code == 0
    assert len(login_calls) == 1
    assert login_calls[0][0] == CONFIG_CATALOG
    assert login_calls[0][1] == DEFAULT_CONFIG
    assert FakeStartupDialog.instances[0].messages == [
        "Loading configuration...",
        "Checking AzCopy...",
        "Checking authentication...",
        "Loading projects...",
        "Opening upload window...",
    ]
    assert FakeStartupDialog.instances[0].close_count == 2


def test_startup_uses_saved_environment_before_token_refresh_and_window_creation(
    qapp, monkeypatch
):
    _patch_startup_dependencies(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
        settings=FakeSettings({"environment": "euphrosyne-staging"}),
    )
    monkeypatch.setattr(qapp, "exec", lambda: 0)

    with pytest.raises(SystemExit) as exit_info:
        gui_module.ConverterGUI.start()

    assert exit_info.value.code == 0
    assert FakeDataUploadWidget.instances[0].config == STAGING_CONFIG


def test_startup_uses_login_returned_environment_for_upload_window(qapp, monkeypatch):
    _patch_startup_dependencies(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
        login_required=True,
    )
    monkeypatch.setattr(
        gui_module,
        "login_user",
        lambda config_catalog, config, settings: STAGING_CONFIG,
    )
    monkeypatch.setattr(qapp, "exec", lambda: 0)

    with pytest.raises(SystemExit) as exit_info:
        gui_module.ConverterGUI.start()

    assert exit_info.value.code == 0
    assert FakeDataUploadWidget.instances[0].config == STAGING_CONFIG


def test_startup_shows_critical_dialog_and_exits_when_project_loading_fails(
    qapp, monkeypatch
):
    _patch_startup_dependencies(
        monkeypatch,
        ProjectLoadingError("Projects response must be a list."),
    )

    with pytest.raises(SystemExit) as exit_info:
        gui_module.ConverterGUI.start()

    assert exit_info.value.code == 1
    assert len(FakeMessageBox.critical_calls) == 1
    assert FakeMessageBox.critical_calls[0][1] == "Projects unavailable"
    assert "Projects response must be a list." in FakeMessageBox.critical_calls[0][2]
    assert FakeStartupDialog.instances[0].close_count == 1


def test_startup_shows_critical_dialog_and_exits_when_project_api_fails(
    qapp, monkeypatch
):
    _patch_startup_dependencies(
        monkeypatch,
        httpx.HTTPStatusError(
            "server error",
            request=httpx.Request(
                "GET", "https://euphrosyne.example/api/lab/projects/"
            ),
            response=httpx.Response(500),
        ),
    )

    with pytest.raises(SystemExit) as exit_info:
        gui_module.ConverterGUI.start()

    assert exit_info.value.code == 1
    assert len(FakeMessageBox.critical_calls) == 1
    assert FakeMessageBox.critical_calls[0][1] == "Projects unavailable"
    assert FakeStartupDialog.instances[0].close_count == 1


@pytest.mark.parametrize(
    "projects",
    [
        [],
        [{"name": "Project A", "slug": "project-a", "runs": []}],
    ],
)
def test_startup_shows_warning_dialog_and_exits_when_no_runs_are_available(
    qapp, monkeypatch, projects
):
    _patch_startup_dependencies(monkeypatch, projects)

    with pytest.raises(SystemExit) as exit_info:
        gui_module.ConverterGUI.start()

    assert exit_info.value.code == 0
    assert len(FakeMessageBox.warning_calls) == 1
    assert FakeMessageBox.warning_calls[0][1] == "No uploadable projects"
    assert FakeStartupDialog.instances[0].close_count == 1
