from data_upload.widget.login import LoginDialog


def test_login_button_requires_email_and_password(qapp):
    dialog = LoginDialog(config={})
    try:
        assert dialog.ok_button.text() == "Log in"
        assert dialog.ok_button.isEnabled() is False

        dialog.email_edit.setText("user@example.com")
        assert dialog.ok_button.isEnabled() is False

        dialog.password_edit.setText("secret")
        assert dialog.ok_button.isEnabled() is True
    finally:
        dialog.close()


def test_login_dialog_returns_credentials(qapp):
    dialog = LoginDialog(config={})
    try:
        dialog.email_edit.setText("user@example.com")
        dialog.password_edit.setText("secret")

        assert dialog.get_credentials() == ("user@example.com", "secret")
    finally:
        dialog.close()
