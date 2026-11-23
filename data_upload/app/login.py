import sys

from PySide6.QtCore import QSettings

from data_upload.config import (
    ENVIRONMENT_SETTING_KEY,
    Config,
    ConfigCatalog,
    resolve_config,
)
from data_upload.euphrosyne.auth import save_refresh_token
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
    # The dialog runs the sign-in and shows its errors.
    if not login_dialog.exec():
        sys.exit(0)

    environment, access_token, refresh_token = login_dialog.get_login_result()
    selected_config = resolve_config(config_catalog, environment)
    settings.setValue("access_token", access_token)
    save_refresh_token(settings, refresh_token)
    settings.setValue(ENVIRONMENT_SETTING_KEY, selected_config["environment"])
    return selected_config
