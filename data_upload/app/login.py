import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from data_upload.config import (
    ENVIRONMENT_SETTING_KEY,
    Config,
    ConfigCatalog,
    resolve_config,
)
from data_upload.euphrosyne.auth import (
    EuphrosyneConnectionError,
    InvalidHermaTokenError,
    login_with_herma_token,
    save_refresh_token,
)
from data_upload.widget.login import LoginDialog


def _show_error(title: str, message: str):
    QMessageBox.critical(None, title, message)


def login_user(
    config_catalog: ConfigCatalog,
    config: Config,
    settings: QSettings,
    allow_environment_change: bool = True,
) -> Config:
    selected_environment = config["environment"]

    while True:
        login_dialog = LoginDialog(
            config=config_catalog,
            selected_environment=selected_environment,
            allow_environment_change=allow_environment_change,
        )
        if not login_dialog.exec():
            sys.exit(0)

        selected_environment, token = login_dialog.get_token_login_data()
        selected_config = resolve_config(config_catalog, selected_environment)
        try:
            access_token, refresh_token = login_with_herma_token(
                host=selected_config["euphrosyne"]["url"],
                raw_token=token,
            )
        except InvalidHermaTokenError as error:
            _show_error("Invalid Herma token", str(error))
            continue
        except EuphrosyneConnectionError as error:
            _show_error("Connection Error", str(error))
            continue

        settings.setValue("access_token", access_token)
        save_refresh_token(settings, refresh_token)
        settings.setValue(ENVIRONMENT_SETTING_KEY, selected_config["environment"])
        return selected_config
