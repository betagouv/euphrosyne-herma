import sys

import httpx
import sentry_sdk
from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QVBoxLayout

from data_upload.app.init import init_access_token, init_azcopy
from data_upload.app.login import login_user
from data_upload.config import load_config
from data_upload.euphrosyne.project import (
    ProjectLoadingError,
    first_project_with_runs,
    list_projects,
)
from data_upload.utils import BUNDLE_DIR, IS_BUNDLED
from data_upload.widget.data_upload import DataUploadWidget
from data_upload.widget.text_edit_stream import TextEditStream

settings = QSettings("Euphrosyne", "Herma")

if IS_BUNDLED:
    ICON_PATH = str(BUNDLE_DIR / "assets" / "icon.png")
else:
    ICON_PATH = str(BUNDLE_DIR / ".." / "assets" / "icon.png")


class StartupDialog:
    def __init__(self, app: QApplication):
        self.app = app
        self.dialog = QDialog()
        self.dialog.setWindowTitle("Starting Euphrosyne Herma")
        self.dialog.setModal(False)
        self.label = QLabel()
        layout = QVBoxLayout(self.dialog)
        layout.addWidget(self.label)
        self.dialog.setMinimumWidth(320)

    def show_message(self, message: str):
        self.label.setText(message)
        self.dialog.show()
        self.app.processEvents()

    def close(self):
        self.dialog.close()
        self.app.processEvents()


class ConverterGUI:
    @staticmethod
    def start():
        app = QApplication.instance() or QApplication(sys.argv)

        app.setWindowIcon(QIcon(ICON_PATH))
        app.setApplicationName("Euphrosyne Herma")
        app.setApplicationDisplayName("Euphrosyne Herma")

        startup_dialog = StartupDialog(app)
        startup_dialog.show_message("Loading configuration...")
        config = load_config()

        startup_dialog.show_message("Checking AzCopy...")
        init_azcopy(app)

        startup_dialog.show_message("Checking authentication...")
        login_required = init_access_token(settings, config)

        if login_required:
            startup_dialog.close()
            login_user(config, settings)
            startup_dialog.show_message("Loading projects...")
        else:
            startup_dialog.show_message("Loading projects...")

        try:
            projects = list_projects(
                host=config["euphrosyne"]["url"],
                access_token=settings.value("access_token"),
            )
        except (ProjectLoadingError, httpx.HTTPError) as e:
            startup_dialog.close()
            QMessageBox.critical(
                None,
                "Projects unavailable",
                f"Could not load projects from Euphrosyne: {e}",
            )
            sys.exit(1)

        if not projects or first_project_with_runs(projects) is None:
            startup_dialog.close()
            QMessageBox.warning(
                None,
                "No uploadable projects",
                "No projects with runs are available for this account.",
            )
            sys.exit(0)

        startup_dialog.show_message("Opening upload window...")
        stdout_stream = TextEditStream()
        sys.stdout = stdout_stream
        sys.stderr = stdout_stream

        w = DataUploadWidget(
            config=config,
            settings=settings,
            stdout_stream=stdout_stream,
        )

        print("\nConfig:", config, "\n")

        w.setWindowTitle("Euphrosyne Herma")
        startup_dialog.close()
        w.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    sentry_sdk.init(
        dsn="https://3ac110bc22bfbcdc13c37d73f5be45de@sentry.incubateur.net/253",
        send_default_pii=True,
    )
    ConverterGUI.start()
