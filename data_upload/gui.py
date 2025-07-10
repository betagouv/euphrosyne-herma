import pathlib
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from data_upload.app.init import init_access_token, init_azcopy
from data_upload.app.login import login_user
from data_upload.config import load_config
from data_upload.widget.data_upload import DataUploadWidget
from data_upload.widget.text_edit_stream import TextEditStream
from data_upload.utils import IS_BUNDLED, BUNDLE_DIR

settings = QSettings("Euphrosyne", "Herma")

if IS_BUNDLED:
    ICON_PATH = str(BUNDLE_DIR / "assets" / "icon.png")
else:
    ICON_PATH = str(BUNDLE_DIR / ".." / "assets" / "icon.png")


class ConverterGUI:
    @staticmethod
    def start():
        app = QApplication(sys.argv)

        app.setWindowIcon(QIcon(ICON_PATH))
        app.setApplicationName("Euphrosyne Herma")
        app.setApplicationDisplayName("Euphrosyne Herma")

        config = load_config()

        init_azcopy(app)

        login_required = init_access_token(settings, config)

        if login_required:
            login_user(config, settings)

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
        w.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    ConverterGUI.start()
