import pytest
from PySide6 import QtWidgets

from data_upload.euphrosyne.auth import (
    AuthorizationPending,
    DeviceAuthorization,
    DeviceAuthorizationError,
    EuphrosyneConnectionError,
)
from data_upload.widget import login as login_module
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


AUTHORIZATION = DeviceAuthorization(
    device_code="device-code",
    user_code="ABCD-EFGH",
    verification_uri="https://staging.euphrosyne.example/identity/o/device",
    verification_uri_complete=(
        "https://staging.euphrosyne.example/identity/o/device?code=ABCD-EFGH"
    ),
    expires_in=300,
    interval=5,
)


@pytest.fixture(name="device_flow")
def device_flow_fixture(monkeypatch):
    """Records calls to Euphrosyne and replays scripted poll results."""
    monkeypatch.delenv("EUPHROSYNE_URL", raising=False)
    calls = {"start": [], "poll": [], "opened": [], "poll_results": []}

    def start(host):
        calls["start"].append(host)
        return AUTHORIZATION

    def poll(host, device_code):
        calls["poll"].append((host, device_code))
        result = calls["poll_results"].pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(login_module, "start_device_authorization", start)
    monkeypatch.setattr(login_module, "poll_device_token", poll)
    monkeypatch.setattr(
        login_module.QDesktopServices,
        "openUrl",
        lambda url: calls["opened"].append(url.toString()),
    )
    return calls


def test_login_dialog_offers_sign_in_with_euphrosyne_only(qapp):
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        assert dialog.findChildren(QtWidgets.QLineEdit) == []
        assert dialog.ok_button.text() == "Sign in with Euphrosyne"
        assert dialog.ok_button.isEnabled() is True
        assert dialog.cancel_button.text() == "Cancel"
        assert dialog.code_label.isHidden()
    finally:
        dialog.close()


def test_sign_in_shows_code_and_opens_euphrosyne(qapp, device_flow):
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        dialog.environment_select.setCurrentIndex(1)
        dialog.ok_button.click()

        assert device_flow["start"] == ["https://staging.euphrosyne.example"]
        assert device_flow["opened"] == [AUTHORIZATION.verification_uri_complete]
        assert dialog.code_label.text() == "ABCD-EFGH"
        assert not dialog.code_label.isHidden()
        assert AUTHORIZATION.verification_uri_complete in dialog.status_label.text()
        assert dialog.ok_button.isEnabled() is False
        assert dialog.environment_select.isEnabled() is False
        assert dialog._poll_timer.isActive()
        assert dialog._poll_timer.interval() == 5000
    finally:
        dialog.reject()


def test_sign_in_completes_when_the_code_is_confirmed(qapp, device_flow):
    device_flow["poll_results"] = [
        AuthorizationPending(),
        AuthorizationPending(slow_down=True),
        ("access", "refresh"),
    ]
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        dialog.ok_button.click()
        dialog.poll()
        dialog.poll()
        assert dialog._poll_timer.interval() == 10000
        dialog.poll()

        assert dialog.result() == QtWidgets.QDialog.Accepted
        assert dialog.get_login_result() == ("euphrosyne", "access", "refresh")
        assert (
            device_flow["poll"] == [("https://euphrosyne.example", "device-code")] * 3
        )
    finally:
        dialog.close()


@pytest.mark.parametrize(
    "error",
    [
        DeviceAuthorizationError("The sign-in was denied on Euphrosyne."),
        EuphrosyneConnectionError(),
    ],
)
def test_sign_in_failure_lets_the_user_try_again(qapp, device_flow, error):
    device_flow["poll_results"] = [error]
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        dialog.ok_button.click()
        dialog.poll()

        assert dialog.status_label.text() == str(error)
        assert dialog.code_label.isHidden()
        assert not dialog._poll_timer.isActive()
        assert dialog.ok_button.text() == "Try again"
        assert dialog.ok_button.isEnabled() is True
        assert dialog.environment_select.isEnabled() is True
        with pytest.raises(RuntimeError):
            dialog.get_login_result()
    finally:
        dialog.close()


def test_sign_in_reports_when_euphrosyne_is_unreachable(qapp, monkeypatch):
    def fail(host):
        raise EuphrosyneConnectionError()

    monkeypatch.setattr(login_module, "start_device_authorization", fail)
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        dialog.ok_button.click()

        assert dialog.status_label.text() == str(EuphrosyneConnectionError())
        assert dialog.ok_button.isEnabled() is True
    finally:
        dialog.close()


def test_expired_code_stops_polling(qapp, device_flow, monkeypatch):
    device_flow["poll_results"] = [AuthorizationPending()]
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    try:
        dialog.ok_button.click()
        monkeypatch.setattr(login_module.time, "monotonic", lambda: float("inf"))
        dialog.poll()

        assert "expired" in dialog.status_label.text()
        assert not dialog._poll_timer.isActive()
    finally:
        dialog.close()


def test_cancel_stops_polling(qapp, device_flow):
    dialog = LoginDialog(config=CONFIG, selected_environment="euphrosyne")
    dialog.ok_button.click()

    dialog.cancel_button.click()

    assert dialog.result() == QtWidgets.QDialog.Rejected
    assert not dialog._poll_timer.isActive()
