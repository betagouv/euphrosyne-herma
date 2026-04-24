from PySide6.QtCore import QSettings, Qt, QThread, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCompleter,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from data_upload.app.azcopy import ProcessWorker
from data_upload.app.login import login_user
from data_upload.config import Config
from data_upload.euphro_tools import (
    EuphrosyneToolsConnectionError,
    EuphrosyneToolsService,
)
from data_upload.euphrosyne.auth import (
    EuphrosyneAuth,
    EuphrosyneAuthenticationError,
    clear_tokens,
    load_refresh_token,
)
from data_upload.euphrosyne.project import (
    Project,
    first_project_with_runs,
    list_projects,
)
from data_upload.widget.data_location import DataLocationInputLayout
from data_upload.widget.data_type import DataTypeCheckboxesLayout
from data_upload.widget.text_edit_stream import TextEditStream


class DataUploadWidget(QWidget):
    """A widget to download a http file to a destination file"""

    projects: list[Project] = []
    selectedProject: str | None = None
    selectedRun: str | None = None

    def __init__(
        self,
        config: Config,
        settings: QSettings,
        stdout_stream: TextEditStream | None = None,
    ):
        super().__init__()
        self.setObjectName("DataUploadWidget")
        self.config = config
        self.settings = settings
        self._upload_in_progress = False

        self.context_box = QTextEdit()
        self.context_box.setObjectName("TransferLog")
        self.context_box.setReadOnly(True)
        self.context_box.setLineWrapMode(QTextEdit.NoWrap)

        if stdout_stream:
            stdout_stream.connect(self.context_box)

        self.context_box.setMinimumHeight(220)

        print(
            "Select a project and run, pick a data type and choose the data folder, "
            "then press Start to begin the transfer."
        )

        self.tools_service = EuphrosyneToolsService(
            host=self.config["euphrosyne-tools"]["url"],
            auth=EuphrosyneAuth(
                access_token=settings.value("access_token"),
                refresh_token=load_refresh_token(settings),
                host=self.config["euphrosyne"]["url"],
                settings=settings,
            ),
        )

        self.projects = projects = list_projects(
            host=self.config["euphrosyne"]["url"],
            access_token=settings.value("access_token"),
        )
        initial_project = first_project_with_runs(projects)
        self.selectedProject = (
            initial_project["slug"]
            if initial_project
            else projects[0]["slug"] if projects else None
        )
        self.selectedRun = (
            initial_project["runs"][0]["label"] if initial_project else None
        )

        self.start_button = QPushButton("Start upload")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setDisabled(True)
        self.logout_button = QPushButton("Sign out")
        self.logout_button.setObjectName("DangerButton")

        def _generate_q_combo_box(items: list[str], placeholder: str):
            combo_box = QComboBox()
            combo_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            combo_box.addItems(items)
            combo_box.setPlaceholderText(placeholder)
            return combo_box

        self.project_select_box = _generate_q_combo_box(
            items=[project["name"] for project in projects],
            placeholder="Search projects...",
        )
        self._configure_searchable_project_select()
        project_label = QLabel("Project")
        project_label.setObjectName("FieldLabel")
        project_label.setBuddy(self.project_select_box)

        self.run_select_box = _generate_q_combo_box(
            items=(
                [run["label"] for run in initial_project["runs"]]
                if initial_project
                else []
            ),
            placeholder="Run",
        )
        self.run_select_box.currentIndexChanged.connect(self.on_run_change)
        if initial_project:
            self.project_select_box.setCurrentIndex(projects.index(initial_project))
        self.project_select_box.currentIndexChanged.connect(self.on_project_change)
        self.project_select_box.editTextChanged.connect(
            self.on_project_search_text_changed
        )
        run_label = QLabel("Run")
        run_label.setObjectName("FieldLabel")
        run_label.setBuddy(self.run_select_box)

        self.data_type_box = DataTypeCheckboxesLayout()
        self.data_type_box.selected.connect(self._validate_form)
        data_type_label = QLabel("Data type")
        data_type_label.setObjectName("FieldLabel")
        data_type_label.setBuddy(self.data_type_box)

        header_layout = self._build_header()

        setup_panel = QFrame()
        setup_panel.setObjectName("Panel")
        setup_layout = QVBoxLayout(setup_panel)
        setup_layout.setContentsMargins(18, 16, 18, 18)
        setup_layout.setSpacing(14)

        setup_title = QLabel("Upload setup")
        setup_title.setObjectName("SectionTitle")
        setup_layout.addWidget(setup_title)

        form_layout = QGridLayout()
        form_layout.setColumnStretch(1, 1)
        form_layout.setHorizontalSpacing(16)
        form_layout.setVerticalSpacing(12)
        form_layout.addWidget(project_label, 0, 0)
        form_layout.addWidget(self.project_select_box, 0, 1)
        form_layout.addWidget(run_label, 1, 0)
        form_layout.addWidget(self.run_select_box, 1, 1)
        form_layout.addWidget(data_type_label, 2, 0)
        form_layout.addWidget(self.data_type_box, 2, 1)

        self.data_folder_input_layout = DataLocationInputLayout()
        self.data_folder_input_layout.data_path_box.textChanged.connect(
            lambda _text: self._validate_form()
        )
        form_layout.addLayout(self.data_folder_input_layout, 3, 0, 1, 2)
        setup_layout.addLayout(form_layout)

        self.status_panel = QFrame()
        self.status_panel.setObjectName("StatusPanel")
        status_layout = QVBoxLayout(self.status_panel)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(4)
        self.status_title_label = QLabel()
        self.status_title_label.setObjectName("StatusTitle")
        self.status_message_label = QLabel()
        self.status_message_label.setObjectName("StatusMessage")
        self.status_message_label.setWordWrap(True)
        status_layout.addWidget(self.status_title_label)
        status_layout.addWidget(self.status_message_label)

        action_layout = QHBoxLayout()
        action_layout.addStretch()
        action_layout.addWidget(self.start_button)

        log_title = QLabel("Transfer log")
        log_title.setObjectName("SectionTitle")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 22, 24, 24)
        main_layout.setSpacing(16)
        main_layout.addLayout(header_layout)
        main_layout.addWidget(setup_panel)
        main_layout.addWidget(self.status_panel)
        main_layout.addLayout(action_layout)
        main_layout.addWidget(log_title)
        main_layout.addWidget(self.context_box, 1)

        self.resize(760, 640)

        self.start_button.clicked.connect(self.on_start)
        self.logout_button.clicked.connect(self.on_logout)
        self._validate_form()

    def _build_header(self) -> QHBoxLayout:
        icon_label = QLabel()
        app = QApplication.instance()
        icon = app.windowIcon() if app else QIcon()
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(52, 52))

        title = QLabel("Euphrosyne Herma")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Upload run data to the Euphrosyne research platform.")
        subtitle.setObjectName("Subtitle")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        header_layout.addWidget(icon_label)
        header_layout.addLayout(text_layout, 1)
        header_layout.addWidget(self.logout_button)
        return header_layout

    def _configure_searchable_project_select(self):
        self.project_select_box.setEditable(True)
        self.project_select_box.setInsertPolicy(QComboBox.NoInsert)
        if self.project_select_box.lineEdit():
            self.project_select_box.lineEdit().setPlaceholderText("Search projects...")

        completer = QCompleter(self.project_select_box.model(), self.project_select_box)
        completer.setCompletionColumn(self.project_select_box.modelColumn())
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.project_select_box.setCompleter(completer)

    @Slot()
    def on_logout(self):
        clear_tokens(self.settings)
        self.context_box.append(
            "Logged out. Please restart the application to log in again."
        )
        self.close()

    @Slot()
    def on_start(self):
        """When user press start button"""
        self._upload_in_progress = True
        self.start_button.setDisabled(True)
        self._set_status(
            "Preparing upload",
            "Creating the destination folders and requesting upload credentials.",
        )

        try:
            self.tools_service.init_folders(
                self.selectedProject,
                self.selectedRun,
            )
        except EuphrosyneAuthenticationError as e:
            self._handle_authentication_error(e)
            return
        except EuphrosyneToolsConnectionError as e:
            QMessageBox.critical(
                self,
                "Connection Error",
                "Failed to connect to Euphrosyne tools server. Please check your connection and try again.",
            )
            self._upload_in_progress = False
            self._set_status(
                "Upload failed",
                "Could not connect to Euphrosyne tools. Check your connection and try again.",
            )
            self._sync_start_button()
            raise e
        except Exception as e:
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize project and run folders: {e}",
            )
            self._upload_in_progress = False
            self._set_status("Upload failed", f"Could not prepare the upload: {e}")
            self._sync_start_button()
            raise e

        try:
            credentials = (
                self.tools_service.get_run_data_upload_shared_access_signature(
                    project_slug=self.selectedProject,
                    run_name=self.selectedRun,
                    data_type=self.data_type_box.selected_data_type.name.lower(),
                )
            )
        except EuphrosyneAuthenticationError as e:
            self._handle_authentication_error(e)
            return
        except Exception as e:
            QMessageBox.critical(
                self,
                "Could not fetch Azure SAS token",
                str(e),
            )
            self._upload_in_progress = False
            self._set_status(
                "Upload failed", f"Could not request upload credentials: {e}"
            )
            self._sync_start_button()
            raise e

        self._set_status(
            "Uploading data",
            "AzCopy is transferring the selected folder. Keep this window open.",
        )
        self._start_azcopy(
            src=self.data_folder_input_layout.data_folder,
            dest=credentials["url"],
            sas_token=credentials["token"],
        )

    def _handle_authentication_error(self, error: EuphrosyneAuthenticationError):
        clear_tokens(self.settings)
        QMessageBox.warning(
            self,
            "Session expired",
            f"{error} Please log in again.",
        )
        login_user(self.config, self.settings)
        self._upload_in_progress = False
        self._set_status(
            "Session expired",
            "You have logged in again. Review the setup, then retry the upload.",
        )
        self.context_box.append("Please retry the upload.")
        self._sync_start_button()

    @Slot(int)
    def on_data_upload_completed(self, return_code: int):
        self._upload_in_progress = False
        if return_code == 0:
            self.context_box.append("Done.")
            self._set_status(
                "Upload complete",
                "The selected data folder was uploaded successfully.",
            )
            self._sync_start_button()
            return

        message = (
            f"Upload failed. AzCopy exited with code {return_code}. "
            "Check the output above for details."
        )
        self.context_box.append(message)
        self._set_status("Upload failed", message)
        self._sync_start_button()
        QMessageBox.critical(self, "Upload failed", message)

    @Slot()
    def on_conversion_failure(self, error: Exception):
        self._upload_in_progress = False
        self._set_status("Upload failed", f"{error} ({type(error).__name__})")
        self._sync_start_button()
        self.context_box.append(f"An error occured : {error} ({type(error).__name__})")
        raise type(error) from error

    @Slot()
    def on_project_change(self, index: int):
        print(f"Project changed to {self.project_select_box.currentText()}")
        self._select_project_at_index(index)

    @Slot(str)
    def on_project_search_text_changed(self, text: str):
        project_index = self._project_index_for_name(text)
        if project_index is None:
            self._clear_project_selection()
            return

        if project_index != self.project_select_box.currentIndex():
            self.project_select_box.setCurrentIndex(project_index)
        else:
            self._select_project_at_index(project_index)

    def _project_index_for_name(self, name: str) -> int | None:
        normalized_name = name.strip().casefold()
        for index, project in enumerate(self.projects):
            if project["name"].casefold() == normalized_name:
                return index
        return None

    def _clear_project_selection(self):
        self.run_select_box.clear()
        self.selectedProject = None
        self.selectedRun = None
        self._validate_form()

    def _select_project_at_index(self, index: int):
        self.run_select_box.clear()
        self.selectedRun = None

        if index < 0 or index >= len(self.projects):
            self.selectedProject = None
            self._validate_form()
            return

        project = self.projects[index]
        self.selectedProject = project["slug"]
        self.run_select_box.addItems([run["label"] for run in project["runs"]])

        if project["runs"]:
            self.run_select_box.setCurrentIndex(0)
            self.selectedRun = self.run_select_box.currentText()
            self._validate_form()
        else:
            self.context_box.append(f"Project {project['name']} has no runs.")
            self._validate_form()

    @Slot()
    def on_run_change(self, index: int):
        print(f"Run changed to {self.run_select_box.currentText()}")
        self.selectedRun = self.run_select_box.currentText() if index >= 0 else None
        self._validate_form()

    @Slot(str)
    def append_azcopy_output(self, line):
        self.context_box.append(line)

    def _validate_form(self, *_args):
        self._sync_start_button()
        if self._upload_in_progress:
            return

        if not self.selectedProject:
            self._set_status(
                "Select a project",
                "Choose a project with at least one run before uploading.",
            )
        elif not self.selectedRun:
            self._set_status(
                "Select a run",
                "The selected project has no run available for upload.",
            )
        elif not self.data_type_box.selected_data_type:
            self._set_status(
                "Select a data type",
                "Choose whether this upload contains raw or processed data.",
            )
        elif not self.data_folder_input_layout.data_folder:
            self._set_status(
                "Choose a data folder",
                "Select the local folder that contains the run data.",
            )
        elif not self.data_folder_input_layout.has_valid_data_folder:
            self._set_status(
                "Invalid data folder",
                "The selected data folder does not exist or is not a folder.",
            )
        else:
            self._set_status(
                "Ready to upload",
                "Review the selected project, run, data type, and folder, then start the upload.",
            )

    def _set_status(self, title: str, message: str):
        self.status_title_label.setText(title)
        self.status_message_label.setText(message)

    def _sync_start_button(self):
        self.start_button.setEnabled(
            self._is_form_valid and not self._upload_in_progress
        )

    @property
    def _is_form_valid(self) -> bool:
        if (
            self.selectedProject
            and self.selectedRun
            and self.data_folder_input_layout.has_valid_data_folder
            and self.data_type_box.selected_data_type
        ):
            return True
        return False

    def _start_azcopy(self, src: str, dest: str, sas_token: str):
        self.thread = QThread()
        self.worker = ProcessWorker(src, dest, sas_token)
        self.worker.moveToThread(self.thread)
        self.worker.output_signal.connect(self.append_azcopy_output)
        self.worker.finished_signal.connect(self.thread.quit)
        self.worker.finished_signal.connect(self.on_data_upload_completed)
        self.thread.started.connect(self.worker.run)
        self.thread.start()
