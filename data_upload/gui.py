import sys

import httpx
import sentry_sdk
from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
)

from data_upload.app.init import init_access_token, init_azcopy
from data_upload.app.login import login_user
from data_upload.config import ENVIRONMENT_SETTING_KEY, load_config, resolve_config
from data_upload.euphrosyne.project import (
    ProjectLoadingError,
    first_project_with_runs,
    list_projects,
)
from data_upload.utils import BUNDLE_DIR, IS_BUNDLED
from data_upload.widget.data_upload import DataUploadWidget
from data_upload.widget.text_edit_stream import TextEditStream
from data_upload.widget.theme import apply_app_theme

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
        self.dialog.setMinimumWidth(420)

        icon_label = QLabel()
        icon_pixmap = QIcon(ICON_PATH).pixmap(44, 44)
        icon_label.setPixmap(icon_pixmap)

        title = QLabel("Euphrosyne Herma")
        title.setObjectName("DialogTitle")
        subtitle = QLabel("Preparing the upload workspace")
        subtitle.setObjectName("Subtitle")

        heading_layout = QVBoxLayout()
        heading_layout.setSpacing(2)
        heading_layout.addWidget(title)
        heading_layout.addWidget(subtitle)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        header_layout.addWidget(icon_label)
        header_layout.addLayout(heading_layout)

        self.label = QLabel()
        self.label.setObjectName("StatusMessage")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)

        layout = QVBoxLayout(self.dialog)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        layout.addLayout(header_layout)
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)

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
        apply_app_theme(app)

        startup_dialog = StartupDialog(app)
        startup_dialog.show_message("Loading configuration...")
        config_catalog = load_config()
        config = resolve_config(
            config_catalog, settings.value(ENVIRONMENT_SETTING_KEY, None)
        )

        startup_dialog.show_message("Checking AzCopy...")
        init_azcopy(app)

        startup_dialog.show_message("Checking authentication...")
        login_required = init_access_token(settings, config)

        if login_required:
            startup_dialog.close()
            config = login_user(config_catalog, config, settings)
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
            config_catalog=config_catalog,
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
