import sys

from PySide6 import QtWidgets
from PySide6.QtCore import QSettings

from data_upload.config import (
    ENVIRONMENT_SETTING_KEY,
    Config,
    ConfigCatalog,
    resolve_config,
)
from data_upload.euphrosyne.auth import euphrosyne_login, save_refresh_token
from data_upload.widget.login import LoginDialog


def login_user(
    config_catalog: ConfigCatalog,
    config: Config,
    settings: QSettings,
    allow_environment_change: bool = True,
) -> Config:
    login_dialog = LoginDialog(
        config=config_catalog,
        selected_environment=config["environment"],
        allow_environment_change=allow_environment_change,
    )
    if login_dialog.exec():
        selected_environment, email, password = login_dialog.get_login_data()
        selected_config = resolve_config(config_catalog, selected_environment)
        tokens = euphrosyne_login(
            host=selected_config["euphrosyne"]["url"],
            email=email,
            password=password,
        )
        if tokens is not None:
            settings.setValue("access_token", tokens[0])
            save_refresh_token(settings, tokens[1])
            settings.setValue(ENVIRONMENT_SETTING_KEY, selected_config["environment"])
            return selected_config

        QtWidgets.QMessageBox.critical(
            None,
            "Login Failed",
            "Failed to log in. Please check your credentials.",
        )
        sys.exit(1)

    sys.exit(0)
