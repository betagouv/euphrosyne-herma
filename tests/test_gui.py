import sys

import httpx
import pytest

from data_upload import gui as gui_module
from data_upload.euphrosyne.project import ProjectLoadingError


class FakeMessageBox:
    critical_calls = []
    warning_calls = []

    @classmethod
    def critical(cls, *args):
        cls.critical_calls.append(args)

    @classmethod
    def warning(cls, *args):
        cls.warning_calls.append(args)


def _patch_startup_dependencies(monkeypatch, projects_or_error):
    FakeMessageBox.critical_calls = []
    FakeMessageBox.warning_calls = []
    monkeypatch.setattr(sys, "argv", ["euphrosyne-herma"])
    monkeypatch.setattr(gui_module, "QMessageBox", FakeMessageBox)
    monkeypatch.setattr(
        gui_module,
        "load_config",
        lambda: {"euphrosyne": {"url": "https://euphrosyne.example"}},
    )
    monkeypatch.setattr(gui_module, "init_azcopy", lambda app: None)
    monkeypatch.setattr(gui_module, "init_access_token", lambda settings, config: False)

    def fake_list_projects(host, access_token):
        if isinstance(projects_or_error, Exception):
            raise projects_or_error
        return projects_or_error

    monkeypatch.setattr(gui_module, "list_projects", fake_list_projects)


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
