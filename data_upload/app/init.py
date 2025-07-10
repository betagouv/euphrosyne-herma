import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from data_upload.azcopy import download_azcopy, is_azcopy_installed
from data_upload.config import Config
from data_upload.euphrosyne.auth import (
    EuphrosyneConnectionError,
    is_token_expired,
    refresh_token,
)


def init_azcopy(app: QApplication):
    """
    Initialize AzCopy by checking if it is installed and if not, downloading and installing it.
    """
    if not is_azcopy_installed():
        progress_dialog = QMessageBox()
        progress_dialog.setWindowTitle("Downloading AzCopy")
        progress_dialog.setText("AzCopy is not installed. Downloading, please wait...")
        progress_dialog.setStandardButtons(QMessageBox.NoButton)
        progress_dialog.setModal(True)
        progress_dialog.show()
        app.processEvents()
        download_azcopy()
        progress_dialog.close()


def init_access_token(settings: QSettings, config: Config):
    """
    Initialize the access token by checking if AzCopy is installed.
    If not, it will download AzCopy.
    """
    access = settings.value("access_token", None)
    refresh = settings.value("refresh_token", None)

    login_required = False

    if access:
        if is_token_expired(access):
            try:
                access = refresh_token(
                    host=config["euphrosyne"]["url"], refresh_token=refresh
                )
            except EuphrosyneConnectionError:
                QMessageBox.critical(
                    None,
                    "Connection Error",
                    "Failed to connect to Euphrosyne server. Please check your connection and try again.",
                )
                sys.exit(1)
            if access is None:
                login_required = True
            else:
                settings.setValue("access_token", access)
    else:
        login_required = True

    return login_required
