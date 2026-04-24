from data_upload.widget.login import LoginDialog


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
