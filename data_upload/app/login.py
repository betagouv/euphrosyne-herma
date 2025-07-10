import sys

from PySide6 import QtWidgets
from PySide6.QtCore import QSettings

from data_upload.config import Config
from data_upload.euphrosyne.auth import euphrosyne_login
from data_upload.widget.login import LoginDialog


def login_user(config: Config, settings: QSettings):
    login_dialog = LoginDialog(config=config)
    if login_dialog.exec():
        tokens = euphrosyne_login(
            host=config["euphrosyne"]["url"],
            email=login_dialog.email_edit.text(),
            password=login_dialog.password_edit.text(),
        )
        if tokens is not None:
            settings.setValue("access_token", tokens[0])
            settings.setValue("refresh_token", tokens[1])
        else:
            QtWidgets.QMessageBox.critical(
                None,
                "Login Failed",
                "Failed to log in. Please check your credentials.",
            )
            sys.exit(1)
    else:
        sys.exit(0)
