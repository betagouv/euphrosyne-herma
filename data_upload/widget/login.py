import html
import time

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices

from data_upload.config import (
    ConfigCatalog,
    get_environment_label,
    list_environment_keys,
    resolve_config,
)
from data_upload.euphrosyne.auth import (
    AuthorizationPending,
    DeviceAuthorization,
    EuphrosyneAuthenticationError,
    EuphrosyneConnectionError,
    poll_device_token,
    start_device_authorization,
)


class LoginDialog(QtWidgets.QDialog):
    def __init__(
        self,
        config: ConfigCatalog,
        selected_environment: str,
        allow_environment_change: bool = True,
    ):
        super().__init__()
        self.config = config
        self.setWindowTitle("Login to Euphrosyne")
        self.setMinimumWidth(480)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QtWidgets.QLabel("Log in to Euphrosyne")
        title.setObjectName("DialogTitle")
        subtitle = QtWidgets.QLabel(
            "Herma opens Euphrosyne in your browser: sign in there and confirm "
            "the code shown below. Only lab administrators can use Herma."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        environment_layout = self._build_form_layout()
        environment_label = QtWidgets.QLabel("Environment")
        environment_label.setObjectName("FieldLabel")
        self.environment_select = QtWidgets.QComboBox()
        self.environment_select.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.environment_select.setMinimumWidth(300)
        for environment in list_environment_keys(config):
            self.environment_select.addItem(
                get_environment_label(environment), environment
            )
        current_index = self.environment_select.findData(selected_environment)
        if current_index >= 0:
            self.environment_select.setCurrentIndex(current_index)
        self._allow_environment_change = allow_environment_change
        self.environment_select.setEnabled(allow_environment_change)
        environment_label.setBuddy(self.environment_select)
        environment_layout.addRow(environment_label, self.environment_select)
        layout.addLayout(environment_layout)

        self._build_code_section(layout)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.ok_button = QtWidgets.QPushButton("Sign in with Euphrosyne")
        self.ok_button.setObjectName("PrimaryButton")
        self.ok_button.setDefault(True)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        layout.addLayout(button_layout)

        self.ok_button.clicked.connect(self.start_sign_in)
        self.cancel_button.clicked.connect(self.reject)

        self._authorization: DeviceAuthorization | None = None
        self._deadline = 0.0
        self._interval = 0
        self._result: tuple[str, str, str] | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setSingleShot(True)
        self._poll_timer.timeout.connect(self.poll)

    @staticmethod
    def _build_form_layout() -> QtWidgets.QFormLayout:
        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(14)
        return form_layout

    def _build_code_section(self, layout: QtWidgets.QVBoxLayout):
        self.code_label = QtWidgets.QLabel()
        self.code_label.setObjectName("DialogTitle")
        self.code_label.setAlignment(Qt.AlignCenter)
        self.code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.code_label.hide()
        layout.addWidget(self.code_label)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("FieldHint")
        self.status_label.setWordWrap(True)
        self.status_label.setOpenExternalLinks(True)
        layout.addWidget(self.status_label)

    def _host(self) -> str:
        selected_config = resolve_config(
            self.config, self.environment_select.currentData()
        )
        return selected_config["euphrosyne"]["url"]

    def start_sign_in(self):
        try:
            authorization = start_device_authorization(self._host())
        except (EuphrosyneAuthenticationError, EuphrosyneConnectionError) as error:
            self._fail(str(error))
            return
        self._authorization = authorization
        self._interval = authorization.interval
        self._deadline = time.monotonic() + authorization.expires_in
        self.environment_select.setEnabled(False)
        self.ok_button.setEnabled(False)
        self.code_label.setText(authorization.user_code)
        self.code_label.show()
        url = authorization.verification_uri_complete
        link = html.escape(url)
        self.status_label.setText(
            "Confirm this code on Euphrosyne, in the page opened in your "
            f'browser. If it did not open, go to <a href="{link}">{link}</a>.'
        )
        QDesktopServices.openUrl(QUrl(url))
        self._schedule_poll()

    def _schedule_poll(self):
        self._poll_timer.start(self._interval * 1000)

    def poll(self):
        if self._authorization is None:
            return
        try:
            access_token, refresh_token = poll_device_token(
                self._host(), self._authorization.device_code
            )
        except AuthorizationPending as pending:
            if time.monotonic() > self._deadline:
                self._fail("The sign-in code expired. Please try again.")
                return
            if pending.slow_down:
                self._interval += 5
            self._schedule_poll()
            return
        except (EuphrosyneAuthenticationError, EuphrosyneConnectionError) as error:
            self._fail(str(error))
            return
        self._result = (
            self.environment_select.currentData(),
            access_token,
            refresh_token,
        )
        self.accept()

    def _fail(self, message: str):
        self._poll_timer.stop()
        self._authorization = None
        self.code_label.hide()
        self.status_label.setText(message)
        self.environment_select.setEnabled(self._allow_environment_change)
        self.ok_button.setText("Try again")
        self.ok_button.setEnabled(True)

    def get_login_result(self) -> tuple[str, str, str]:
        """Return the environment, the access token and the refresh token."""
        if self._result is None:
            raise RuntimeError("The sign-in did not complete.")
        return self._result

    def reject(self):
        self._poll_timer.stop()
        super().reject()
