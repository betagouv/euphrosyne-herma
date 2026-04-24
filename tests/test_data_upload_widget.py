from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QCompleter

from data_upload.euphrosyne.auth import EuphrosyneAuthenticationError
from data_upload.widget import data_upload as data_upload_module
from data_upload.widget.data_upload import DataUploadWidget


class FakeSettings:
    def __init__(self):
        self.values = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        }

    def value(self, key, default=None):
        return self.values.get(key, default)

    def remove(self, key):
        self.values.pop(key, None)


class FakeMessageBox:
    critical_calls = []
    warning_calls = []

    @classmethod
    def critical(cls, *args):
        cls.critical_calls.append(args)

    @classmethod
    def warning(cls, *args):
        cls.warning_calls.append(args)


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

CONFIG = {
    "environment": "euphrosyne",
    "euphrosyne": {"url": "https://euphrosyne.example"},
    "euphrosyne-tools": {"url": "https://tools.example"},
}


def _widget(monkeypatch, projects):
    monkeypatch.setattr(
        data_upload_module, "list_projects", lambda host, access_token: projects
    )
    monkeypatch.setattr(
        data_upload_module, "load_refresh_token", lambda settings: "refresh-token"
    )
    widget = DataUploadWidget(
        config_catalog=CONFIG_CATALOG,
        config=CONFIG,
        settings=FakeSettings(),
    )
    return widget


class FakeToolsService:
    def __init__(self, init_error=None, sas_error=None):
        self.init_error = init_error
        self.sas_error = sas_error

    def init_folders(self, project_name, run_name):
        if self.init_error:
            raise self.init_error

    def get_run_data_upload_shared_access_signature(
        self, project_slug, run_name, data_type
    ):
        if self.sas_error:
            raise self.sas_error
        return {"url": "https://storage.example/share", "token": "sas-token"}


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


def test_upload_completion_success_appends_done_updates_status_and_reenables_start(
    qapp, monkeypatch, tmp_path
):
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    try:
        widget.data_folder_input_layout.data_path_box.setText(str(tmp_path))
        widget.start_button.setDisabled(True)

        widget.on_data_upload_completed(0)

        assert widget.start_button.isEnabled() is True
        assert widget.status_title_label.text() == "Upload complete"
        assert "Done." in widget.context_box.toPlainText()
        assert "Upload failed" not in widget.context_box.toPlainText()
    finally:
        widget.close()


def test_upload_completion_failure_appends_error_updates_status_and_reenables_start(
    qapp, monkeypatch, tmp_path
):
    FakeMessageBox.critical_calls = []
    monkeypatch.setattr(data_upload_module, "QMessageBox", FakeMessageBox)
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    try:
        widget.data_folder_input_layout.data_path_box.setText(str(tmp_path))
        widget.start_button.setDisabled(True)

        widget.on_data_upload_completed(1)

        expected_message = (
            "Upload failed. AzCopy exited with code 1. "
            "Check the output above for details."
        )
        assert widget.start_button.isEnabled() is True
        assert widget.status_title_label.text() == "Upload failed"
        assert widget.status_message_label.text() == expected_message
        assert expected_message in widget.context_box.toPlainText()
        assert "Done." not in widget.context_box.toPlainText()
        assert len(FakeMessageBox.critical_calls) == 1
        assert FakeMessageBox.critical_calls[0][1:] == (
            "Upload failed",
            expected_message,
        )
    finally:
        widget.close()


def test_logout_clears_tokens_appends_message_and_closes_window(qapp, monkeypatch):
    cleared_settings = []

    def fake_clear_tokens(settings):
        cleared_settings.append(settings)
        settings.remove("access_token")
        settings.remove("refresh_token")

    monkeypatch.setattr(data_upload_module, "clear_tokens", fake_clear_tokens)
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    widget.show()

    assert widget.logout_button.text() == "Sign out"
    assert widget.logout_button.objectName() == "DangerButton"

    widget.on_logout()

    assert cleared_settings == [widget.settings]
    assert widget.settings.values == {}
    assert (
        "Logged out. Please restart the application to log in again."
        in widget.context_box.toPlainText()
    )
    assert widget.isVisible() is False


def test_auth_failure_during_folder_init_clears_tokens_prompts_login_and_stops(
    qapp, monkeypatch
):
    FakeMessageBox.warning_calls = []
    login_calls = []
    monkeypatch.setattr(data_upload_module, "QMessageBox", FakeMessageBox)
    monkeypatch.setattr(
        data_upload_module,
        "login_user",
        lambda config_catalog, config, settings, allow_environment_change=True: (
            login_calls.append(
                (config_catalog, config, settings, allow_environment_change)
            )
            or config
        ),
    )
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    try:
        widget.tools_service = FakeToolsService(
            init_error=EuphrosyneAuthenticationError("Session expired.")
        )
        widget.start_button.setDisabled(True)

        widget.on_start()

        assert widget.settings.values == {}
        assert login_calls == [(CONFIG_CATALOG, CONFIG, widget.settings, False)]
        assert len(FakeMessageBox.warning_calls) == 1
        assert FakeMessageBox.warning_calls[0][1] == "Session expired"
        assert widget.status_title_label.text() == "Session expired"
        assert "Please retry the upload." in widget.context_box.toPlainText()
        assert widget.start_button.isEnabled() is False
    finally:
        widget.close()


def test_auth_failure_during_sas_request_clears_tokens_prompts_login_and_stops(
    qapp, monkeypatch
):
    FakeMessageBox.warning_calls = []
    login_calls = []
    monkeypatch.setattr(data_upload_module, "QMessageBox", FakeMessageBox)
    monkeypatch.setattr(
        data_upload_module,
        "login_user",
        lambda config_catalog, config, settings, allow_environment_change=True: (
            login_calls.append(
                (config_catalog, config, settings, allow_environment_change)
            )
            or config
        ),
    )
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    try:
        widget.tools_service = FakeToolsService(
            sas_error=EuphrosyneAuthenticationError("Session expired.")
        )
        widget.start_button.setDisabled(True)

        widget.on_start()

        assert widget.settings.values == {}
        assert login_calls == [(CONFIG_CATALOG, CONFIG, widget.settings, False)]
        assert len(FakeMessageBox.warning_calls) == 1
        assert FakeMessageBox.warning_calls[0][1] == "Session expired"
        assert widget.status_title_label.text() == "Session expired"
        assert "Please retry the upload." in widget.context_box.toPlainText()
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
        assert widget.selectedProject == "project-a"
        assert widget.selectedRun is None
        assert widget.project_select_box.count() == 1
        assert widget.run_select_box.count() == 0
        assert widget.start_button.isEnabled() is False
        assert widget.status_title_label.text() == "Select a run"
    finally:
        widget.close()


def test_typed_existing_data_folder_enables_start(qapp, monkeypatch, tmp_path):
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    try:
        widget.data_folder_input_layout.data_path_box.setText(str(tmp_path))

        assert widget.start_button.isEnabled() is True
        assert widget.start_button.text() == "Start upload"
        assert widget.status_title_label.text() == "Ready to upload"
        assert "Ready ?" not in widget.context_box.toPlainText()
    finally:
        widget.close()


def test_typed_missing_data_folder_keeps_start_disabled(qapp, monkeypatch, tmp_path):
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    try:
        widget.data_folder_input_layout.data_path_box.setText(str(tmp_path / "missing"))

        assert widget.start_button.isEnabled() is False
        assert widget.status_title_label.text() == "Invalid data folder"
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
        assert widget.selectedProject == "project-b"
        assert widget.run_select_box.currentText() == "Run 1"
        assert widget.selectedRun == "Run 1"
    finally:
        widget.close()


def test_project_dropdown_is_searchable(qapp, monkeypatch):
    widget = _widget(
        monkeypatch,
        [
            {
                "name": "Alpha Trial",
                "slug": "alpha-trial",
                "runs": [{"label": "Run 1"}],
            },
            {
                "name": "Beta Upload",
                "slug": "beta-upload",
                "runs": [{"label": "Run 2"}],
            },
        ],
    )
    try:
        combo = widget.project_select_box
        completer = combo.completer()
        completer.setCompletionPrefix("upload")
        matches = [
            completer.completionModel().index(row, 0).data()
            for row in range(completer.completionModel().rowCount())
        ]

        assert combo.isEditable() is True
        assert combo.insertPolicy() == QComboBox.NoInsert
        assert combo.lineEdit().placeholderText() == "Search projects..."
        assert completer.caseSensitivity() == Qt.CaseInsensitive
        assert completer.filterMode() == Qt.MatchContains
        assert completer.completionMode() == QCompleter.PopupCompletion
        assert matches == ["Beta Upload"]
    finally:
        widget.close()


def test_typing_existing_project_name_selects_project_and_updates_runs(
    qapp, monkeypatch
):
    widget = _widget(
        monkeypatch,
        [
            {
                "name": "Project A",
                "slug": "project-a",
                "runs": [{"label": "Run 1"}],
            },
            {
                "name": "Project B",
                "slug": "project-b",
                "runs": [{"label": "Run 2"}],
            },
        ],
    )
    try:
        widget.project_select_box.setEditText("Project B")

        assert widget.selectedProject == "project-b"
        assert widget.selectedRun == "Run 2"
        assert widget.run_select_box.count() == 1
        assert widget.run_select_box.currentText() == "Run 2"
    finally:
        widget.close()


def test_typing_unknown_project_clears_selection_without_adding_project(
    qapp, monkeypatch, tmp_path
):
    widget = _widget(
        monkeypatch,
        [
            {
                "name": "Project A",
                "slug": "project-a",
                "runs": [{"label": "Run 1"}],
            }
        ],
    )
    try:
        widget.data_folder_input_layout.data_path_box.setText(str(tmp_path))
        original_count = widget.project_select_box.count()

        widget.project_select_box.setEditText("Unknown project")

        assert widget.project_select_box.count() == original_count
        assert widget.selectedProject is None
        assert widget.selectedRun is None
        assert widget.run_select_box.count() == 0
        assert widget.start_button.isEnabled() is False
        assert widget.status_title_label.text() == "Select a project"
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

        assert widget.selectedProject == "project-a"
        assert widget.selectedRun is None
        assert widget.run_select_box.count() == 0
        assert widget.start_button.isEnabled() is False
        assert widget.status_title_label.text() == "Select a run"
        assert "Project Project A has no runs." in widget.context_box.toPlainText()
    finally:
        widget.close()


def test_start_upload_disables_button_and_sets_uploading_status(
    qapp, monkeypatch, tmp_path
):
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    started_uploads = []
    try:
        widget.data_folder_input_layout.data_path_box.setText(str(tmp_path))
        widget.tools_service = FakeToolsService()
        widget._start_azcopy = lambda src, dest, sas_token: started_uploads.append(
            (src, dest, sas_token)
        )

        widget.on_start()

        assert widget.start_button.isEnabled() is False
        assert widget.status_title_label.text() == "Uploading data"
        assert started_uploads == [
            (str(tmp_path), "https://storage.example/share", "sas-token")
        ]
    finally:
        widget.close()


def test_auth_failure_revalidates_valid_form_after_login(qapp, monkeypatch, tmp_path):
    FakeMessageBox.warning_calls = []
    monkeypatch.setattr(data_upload_module, "QMessageBox", FakeMessageBox)
    monkeypatch.setattr(
        data_upload_module,
        "login_user",
        lambda config_catalog, config, settings, allow_environment_change=True: config,
    )
    widget = _widget(
        monkeypatch,
        [{"name": "Project A", "slug": "project-a", "runs": [{"label": "Run 1"}]}],
    )
    try:
        widget.data_folder_input_layout.data_path_box.setText(str(tmp_path))
        widget.tools_service = FakeToolsService(
            init_error=EuphrosyneAuthenticationError("Session expired.")
        )

        widget.on_start()

        assert widget.status_title_label.text() == "Session expired"
        assert widget.start_button.isEnabled() is True
    finally:
        widget.close()
