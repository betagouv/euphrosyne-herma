from data_upload.widget import data_upload as data_upload_module
from data_upload.widget.data_upload import DataUploadWidget


class FakeSettings:
    def value(self, key, default=None):
        values = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        }
        return values.get(key, default)


CONFIG = {
    "euphrosyne": {"url": "https://euphrosyne.example"},
    "euphrosyne-tools": {"url": "https://tools.example"},
}


def _widget(monkeypatch, projects):
    monkeypatch.setattr(
        data_upload_module, "list_projects", lambda host, access_token: projects
    )
    widget = DataUploadWidget(config=CONFIG, settings=FakeSettings())
    return widget


def test_empty_project_list_does_not_crash_and_keeps_start_disabled(qapp, monkeypatch):
    widget = _widget(monkeypatch, [])
    try:
        assert widget.selectedProject is None
        assert widget.selectedRun is None
        assert widget.project_select_box.count() == 0
        assert widget.run_select_box.count() == 0
        assert widget.start_button.isEnabled() is False
    finally:
        widget.close()


def test_project_without_runs_does_not_crash_and_keeps_start_disabled(
    qapp, monkeypatch
):
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": []}],
    )
    try:
        assert widget.selectedProject == "Project A"
        assert widget.selectedRun is None
        assert widget.project_select_box.count() == 1
        assert widget.run_select_box.count() == 0
        assert widget.start_button.isEnabled() is False
    finally:
        widget.close()


def test_first_project_with_runs_is_selected_initially(qapp, monkeypatch):
    widget = _widget(
        monkeypatch,
        [
            {"name": "Project A", "slug": "project-a", "runs": []},
            {
                "name": "Project B",
                "slug": "project-b",
                "runs": [{"label": "Run 1"}],
            },
        ],
    )
    try:
        assert widget.project_select_box.currentText() == "Project B"
        assert widget.selectedProject == "Project B"
        assert widget.run_select_box.currentText() == "Run 1"
        assert widget.selectedRun == "Run 1"
    finally:
        widget.close()


def test_switching_to_project_without_runs_clears_run_and_disables_start(
    qapp, monkeypatch
):
    widget = _widget(
        monkeypatch,
        [
            {"name": "Project A", "slug": "project-a", "runs": []},
            {
                "name": "Project B",
                "slug": "project-b",
                "runs": [{"label": "Run 1"}],
            },
        ],
    )
    try:
        widget.start_button.setDisabled(False)

        widget.project_select_box.setCurrentIndex(0)

        assert widget.selectedProject == "Project A"
        assert widget.selectedRun is None
        assert widget.run_select_box.count() == 0
        assert widget.start_button.isEnabled() is False
        assert "Project Project A has no runs." in widget.context_box.toPlainText()
    finally:
        widget.close()
