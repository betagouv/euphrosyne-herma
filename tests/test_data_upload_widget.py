from data_upload.widget import data_upload as data_upload_module
from data_upload.widget.data_upload import DataUploadWidget


class FakeSettings:
    def value(self, key, default=None):
        values = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        }
        return values.get(key, default)


class FakeMessageBox:
    critical_calls = []

    @classmethod
    def critical(cls, *args):
        cls.critical_calls.append(args)


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


def test_upload_completion_success_appends_done_and_reenables_start(qapp, monkeypatch):
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    try:
        widget.start_button.setDisabled(True)

        widget.on_data_upload_completed(0)

        assert widget.start_button.isEnabled() is True
        assert "Done." in widget.context_box.toPlainText()
        assert "Upload failed" not in widget.context_box.toPlainText()
    finally:
        widget.close()


def test_upload_completion_failure_appends_error_shows_dialog_and_reenables_start(
    qapp, monkeypatch
):
    FakeMessageBox.critical_calls = []
    monkeypatch.setattr(data_upload_module, "QMessageBox", FakeMessageBox)
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    try:
        widget.start_button.setDisabled(True)

        widget.on_data_upload_completed(1)

        expected_message = (
            "Upload failed. AzCopy exited with code 1. "
            "Check the output above for details."
        )
        assert widget.start_button.isEnabled() is True
        assert expected_message in widget.context_box.toPlainText()
        assert "Done." not in widget.context_box.toPlainText()
        assert len(FakeMessageBox.critical_calls) == 1
        assert FakeMessageBox.critical_calls[0][1:] == (
            "Upload failed",
            expected_message,
        )
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
