from PySide6.QtCore import QSettings, QThread, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from data_upload.widget.text_edit_stream import TextEditStream

from data_upload.app.azcopy import ProcessWorker
from data_upload.config import Config
from data_upload.euphro_tools import (
    EuphrosyneToolsConnectionError,
    EuphrosyneToolsService,
)
from data_upload.euphrosyne.auth import EuphrosyneAuth
from data_upload.euphrosyne.project import Project, list_projects
from data_upload.widget.data_location import DataLocationInputLayout
from data_upload.widget.data_type import DataTypeCheckboxesLayout


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
        self.config = config

        self.context_box = QTextEdit()
        self.context_box.setReadOnly(True)

        if stdout_stream:
            stdout_stream.connect(self.context_box)

        self.context_box.setMinimumHeight(300)

        print(
            "Select a project and run, pick a data type and choose the data folder, "
            "then press Start to begin the transfer."
        )

        self.tools_service = EuphrosyneToolsService(
            host=self.config["euphrosyne-tools"]["url"],
            auth=EuphrosyneAuth(
                access_token=settings.value("access_token"),
                refresh_token=settings.value("refresh_token"),
                host=self.config["euphrosyne"]["url"],
                settings=settings,
            ),
        )

        self.projects = projects = list_projects(
            host=self.config["euphrosyne"]["url"],
            access_token=settings.value("access_token"),
        )
        self.selectedProject = projects[0]["name"] if projects else None
        self.selectedRun = (
            projects[0]["runs"][0]["label"]
            if projects[0] and projects[0]["runs"]
            else None
        )

        self.start_button = QPushButton("Start")
        self.start_button.setDisabled(True)

        def _generate_q_combo_box(items: list[str], placeholder: str):
            combo_box = QComboBox()
            combo_box.addItems(items)
            combo_box.setPlaceholderText(placeholder)
            return combo_box

        self.project_select_box = _generate_q_combo_box(
            items=[project["name"] for project in projects],
            placeholder="Project",
        )
        self.project_select_box.currentIndexChanged.connect(self.on_project_change)
        project_label = QLabel("Project")
        project_label.setBuddy(self.project_select_box)

        self.run_select_box = _generate_q_combo_box(
            items=[run["label"] for run in projects[0]["runs"]],
            placeholder="Run",
        )
        self.run_select_box.currentIndexChanged.connect(self.on_run_change)
        run_label = QLabel("Run")
        run_label.setBuddy(self.run_select_box)

        self.data_type_box = DataTypeCheckboxesLayout()
        self.data_type_box.selected.connect(self._validate_form)
        data_type_label = QLabel("Data type")
        data_type_label.setBuddy(self.data_type_box)

        # buttons bar layout
        buttonslayout = QHBoxLayout()
        buttonslayout.addStretch()
        buttonslayout.addWidget(self.start_button)

        # main layout
        vlayout = QVBoxLayout(self)
        vlayout.addWidget(project_label)
        vlayout.addWidget(self.project_select_box)
        vlayout.addWidget(run_label)
        vlayout.addWidget(self.run_select_box)
        vlayout.addWidget(data_type_label)
        vlayout.addWidget(self.data_type_box)
        vlayout.addSpacing(12)
        self.data_folder_input_layout = DataLocationInputLayout()
        self.data_folder_input_layout.folder_selected.connect(self._validate_form)
        vlayout.addLayout(self.data_folder_input_layout)
        vlayout.addLayout(buttonslayout)
        vlayout.addWidget(self.context_box)

        self.resize(600, 300)

        self.start_button.clicked.connect(self.on_start)
        self.start_button.setDisabled(True)

    @Slot()
    def on_start(self):
        """When user press start button"""

        try:
            self.tools_service.init_folders(
                self.selectedProject,
                self.selectedRun,
            )
        except EuphrosyneToolsConnectionError as e:
            QMessageBox.critical(
                self,
                "Connection Error",
                "Failed to connect to Euphrosyne tools server. Please check your connection and try again.",
            )
            raise e
        except Exception as e:
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize project and run folders: {e}",
            )
            raise e

        try:
            credentials = (
                self.tools_service.get_run_data_upload_shared_access_signature(
                    project_name=self.selectedProject,
                    run_name=self.selectedRun,
                    data_type=self.data_type_box.selected_data_type.name.lower(),
                )
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Could not fetch Azure SAS token",
                str(e),
            )
            raise e

        self._start_azcopy(
            src=self.data_folder_input_layout.data_folder,
            dest=credentials["url"],
            sas_token=credentials["token"],
        )

    @Slot()
    def on_data_upload_completed(self):
        self.start_button.setDisabled(False)
        self.context_box.append("Done.")

    @Slot()
    def on_conversion_failure(self, error: Exception):
        self.start_button.setDisabled(False)
        self.context_box.append(f"An error occured : {error} ({type(error).__name__})")
        raise type(error) from error

    @Slot()
    def on_project_change(self, index: int):
        print(f"Project changed to {self.project_select_box.currentText()}")
        self.selectedProject = self.project_select_box.currentText()
        self.run_select_box.clear()
        self.run_select_box.addItems(
            [run["label"] for run in self.projects[index]["runs"]]
        )
        self.run_select_box.setCurrentIndex(0)

    @Slot()
    def on_run_change(self, index: int):
        print(f"Run changed to {self.run_select_box.currentText()}")
        self.selectedRun = self.run_select_box.currentText()

    @Slot(str)
    def append_azcopy_output(self, line):
        self.context_box.append(line)

    def _validate_form(self):
        if (
            self.selectedProject
            and self.selectedRun
            and self.data_folder_input_layout.selected_folder
            and self.data_type_box.selected_data_type
        ):
            self.start_button.setDisabled(False)
            self.context_box.append("Ready ?\n\n")

    def _start_azcopy(self, src: str, dest: str, sas_token: str):
        self.thread = QThread()
        self.worker = ProcessWorker(src, dest, sas_token)
        self.worker.moveToThread(self.thread)
        self.worker.output_signal.connect(self.append_azcopy_output)
        self.worker.finished_signal.connect(self.thread.quit)
        self.worker.finished_signal.connect(self.on_data_upload_completed)
        self.thread.started.connect(self.worker.run)
        self.thread.start()
