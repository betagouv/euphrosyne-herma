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
    EuphrosyneLoginThrottledError,
    EuphrosyneTokenLoginRequiredError,
    InvalidHermaTokenError,
    euphrosyne_login,
    login_with_herma_token,
    save_refresh_token,
)
from data_upload.widget.login import (
    LOGIN_MODE_PASSWORD,
    LOGIN_MODE_TOKEN,
    LoginDialog,
)


def _show_error(title: str, message: str):
    QMessageBox.critical(None, title, message)


def login_user(
    config_catalog: ConfigCatalog,
    config: Config,
    settings: QSettings,
    allow_environment_change: bool = True,
) -> Config:
    selected_environment = config["environment"]
    login_mode = LOGIN_MODE_PASSWORD
    email = ""

    while True:
        login_dialog = LoginDialog(
            config=config_catalog,
            selected_environment=selected_environment,
            allow_environment_change=allow_environment_change,
            login_mode=login_mode,
            email=email,
        )
        if not login_dialog.exec():
            sys.exit(0)

        login_mode = login_dialog.get_login_mode()
        try:
            if login_mode == LOGIN_MODE_TOKEN:
                selected_environment, token = login_dialog.get_token_login_data()
                selected_config = resolve_config(config_catalog, selected_environment)
                tokens = login_with_herma_token(
                    host=selected_config["euphrosyne"]["url"],
                    raw_token=token,
                )
            else:
                selected_environment, email, password = login_dialog.get_login_data()
                selected_config = resolve_config(config_catalog, selected_environment)
                tokens = euphrosyne_login(
                    host=selected_config["euphrosyne"]["url"],
                    email=email,
                    password=password,
                )
        except EuphrosyneTokenLoginRequiredError:
            _show_error(
                "Herma token required",
                "Password login is not allowed for this account (for example "
                "lab administrators, who must use two-factor authentication).\n\n"
                "Use the “Paste a Herma token” tab: generate a token on "
                "Euphrosyne, then paste it in Herma.",
            )
            login_mode = LOGIN_MODE_TOKEN
            continue
        except EuphrosyneLoginThrottledError as error:
            _show_error("Login Failed", str(error))
            continue
        except InvalidHermaTokenError as error:
            _show_error("Invalid Herma token", str(error))
            continue
        except EuphrosyneConnectionError as error:
            _show_error("Connection Error", str(error))
            continue

        if tokens is None:
            _show_error(
                "Login Failed",
                "Failed to log in. Please check your credentials.",
            )
            continue

        settings.setValue("access_token", tokens[0])
        save_refresh_token(settings, tokens[1])
        settings.setValue(ENVIRONMENT_SETTING_KEY, selected_config["environment"])
        return selected_config
