from PySide6 import QtWidgets

from data_upload.widget import login as login_module
from data_upload.widget.login import (
    LOGIN_MODE_PASSWORD,
    LOGIN_MODE_TOKEN,
    LoginDialog,
)

CONFIG = {
    "default-environment": "euphrosyne",
    "environments": {
        "euphrosyne": {
            "url": "https://euphrosyne.example",
            "euphro-tools-url": "https://tools.example",
        },
        "euphrosyne-staging": {
            "url": "https://staging.euphrosyne.example",
            "euphro-tools-url": "https://staging.tools.example",
        },
    },
}


def test_login_dialog_shows_environment_selector_with_default_choice(qapp):
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        assert dialog.environment_select.count() == 2
        assert dialog.environment_select.itemText(0) == "Euphrosyne"
        assert dialog.environment_select.itemData(0) == "euphrosyne"
        assert dialog.environment_select.itemText(1) == "Euphrosyne staging"
        assert dialog.environment_select.itemData(1) == "euphrosyne-staging"
        assert dialog.environment_select.currentData() == "euphrosyne"
        assert dialog.environment_select.isEnabled() is True
    finally:
        dialog.close()


def test_login_button_requires_email_and_password(qapp):
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        assert dialog.ok_button.text() == "Log in"
        assert dialog.ok_button.isEnabled() is False

        dialog.email_edit.setText("user@example.com")
        assert dialog.ok_button.isEnabled() is False

        dialog.password_edit.setText("secret")
        assert dialog.ok_button.isEnabled() is True
    finally:
        dialog.close()


def test_login_dialog_returns_selected_environment_and_credentials(qapp):
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        dialog.environment_select.setCurrentIndex(1)
        dialog.email_edit.setText("user@example.com")
        dialog.password_edit.setText("secret")

        assert dialog.get_credentials() == ("user@example.com", "secret")
        assert dialog.get_login_data() == (
            "euphrosyne-staging",
            "user@example.com",
            "secret",
        )
    finally:
        dialog.close()


def test_login_dialog_disables_environment_selector_during_relogin(qapp):
    dialog = LoginDialog(
        config=CONFIG,
        selected_environment="euphrosyne-staging",
        allow_environment_change=False,
    )
    try:
        assert dialog.environment_select.currentData() == "euphrosyne-staging"
        assert dialog.environment_select.isEnabled() is False
    finally:
        dialog.close()


def test_login_dialog_defaults_to_password_mode(qapp):
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        assert dialog.get_login_mode() == LOGIN_MODE_PASSWORD
        assert dialog.mode_tabs.tabText(1) == "Paste a Herma token"
    finally:
        dialog.close()


def test_login_button_requires_token_in_token_mode(qapp):
    dialog = LoginDialog(
        config=CONFIG, selected_environment="euphrosyne", login_mode=LOGIN_MODE_TOKEN
    )
    try:
        assert dialog.get_login_mode() == LOGIN_MODE_TOKEN
        assert dialog.ok_button.isEnabled() is False

        dialog.token_edit.setText("   ")
        assert dialog.ok_button.isEnabled() is False

        dialog.token_edit.setText("header.payload.signature")
        assert dialog.ok_button.isEnabled() is True
        assert dialog.token_edit.echoMode() == QtWidgets.QLineEdit.Password

        dialog.set_login_mode(LOGIN_MODE_PASSWORD)
        assert dialog.ok_button.isEnabled() is False
    finally:
        dialog.close()


def test_login_dialog_returns_selected_environment_and_token(qapp):
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        dialog.environment_select.setCurrentIndex(1)
        dialog.mode_tabs.setCurrentIndex(1)
        dialog.token_edit.setText("header.payload.signature")

        assert dialog.get_login_mode() == LOGIN_MODE_TOKEN
        assert dialog.get_token_login_data() == (
            "euphrosyne-staging",
            "header.payload.signature",
        )
    finally:
        dialog.close()


def test_login_dialog_prefills_email(qapp):
    dialog = LoginDialog(
        config=CONFIG, selected_environment="euphrosyne", email="user@example.com"
    )
    try:
        assert dialog.email_edit.text() == "user@example.com"
    finally:
        dialog.close()


def test_login_dialog_herma_token_url_follows_selected_environment(qapp, monkeypatch):
    monkeypatch.delenv("EUPHROSYNE_URL", raising=False)
    opened_urls = []
    monkeypatch.setattr(
        login_module.QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()),
    )
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        assert dialog.get_herma_token_url() == "https://euphrosyne.example/herma-token/"

        dialog.environment_select.setCurrentIndex(1)
        dialog.open_token_page_button.click()

        assert opened_urls == ["https://staging.euphrosyne.example/herma-token/"]
    finally:
        dialog.close()
