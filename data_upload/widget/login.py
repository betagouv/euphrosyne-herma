from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

from data_upload.config import (
    ConfigCatalog,
    get_environment_label,
    list_environment_keys,
    resolve_config,
)
from data_upload.euphrosyne.auth import get_herma_token_url

LOGIN_MODE_PASSWORD = "password"
LOGIN_MODE_TOKEN = "token"


class LoginDialog(QtWidgets.QDialog):
    def __init__(
        self,
        config: ConfigCatalog,
        selected_environment: str,
        allow_environment_change: bool = True,
        login_mode: str = LOGIN_MODE_PASSWORD,
        email: str = "",
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
            "Log in with your Euphrosyne credentials, or paste a Herma token."
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
        self.environment_select.setEnabled(allow_environment_change)
        environment_label.setBuddy(self.environment_select)
        environment_layout.addRow(environment_label, self.environment_select)
        layout.addLayout(environment_layout)

        self.mode_tabs = QtWidgets.QTabWidget()
        self.mode_tabs.addTab(self._build_password_tab(email), "Email and password")
        self.mode_tabs.addTab(self._build_token_tab(), "Paste a Herma token")
        layout.addWidget(self.mode_tabs)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.ok_button = QtWidgets.QPushButton("Log in")
        self.ok_button.setObjectName("PrimaryButton")
        self.ok_button.setDefault(True)
        self.ok_button.setDisabled(True)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        layout.addLayout(button_layout)

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.email_edit.textChanged.connect(self._validate_credentials)
        self.password_edit.textChanged.connect(self._validate_credentials)
        self.token_edit.textChanged.connect(self._validate_credentials)
        self.mode_tabs.currentChanged.connect(self._validate_credentials)
        self.open_token_page_button.clicked.connect(self.open_herma_token_page)

        self.set_login_mode(login_mode)

    @staticmethod
    def _build_form_layout() -> QtWidgets.QFormLayout:
        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(14)
        return form_layout

    def _build_password_tab(self, email: str) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        form_layout = self._build_form_layout()
        form_layout.setContentsMargins(12, 12, 12, 12)

        email_label = QtWidgets.QLabel("Email")
        email_label.setObjectName("FieldLabel")
        self.email_edit = QtWidgets.QLineEdit()
        self.email_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.email_edit.setMinimumWidth(300)
        self.email_edit.setPlaceholderText("name@example.com")
        self.email_edit.setText(email)
        email_label.setBuddy(self.email_edit)
        form_layout.addRow(email_label, self.email_edit)

        password_label = QtWidgets.QLabel("Password")
        password_label.setObjectName("FieldLabel")
        self.password_edit = QtWidgets.QLineEdit()
        self.password_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.password_edit.setMinimumWidth(300)
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password_edit.setPlaceholderText("Enter your password")
        password_label.setBuddy(self.password_edit)
        form_layout.addRow(password_label, self.password_edit)

        tab.setLayout(form_layout)
        return tab

    def _build_token_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        tab_layout = QtWidgets.QVBoxLayout(tab)
        tab_layout.setContentsMargins(12, 12, 12, 12)
        tab_layout.setSpacing(10)

        explanation = QtWidgets.QLabel(
            "Lab administrators must use a Herma token. Open the Herma token "
            "page on Euphrosyne, log in with two-factor authentication, "
            "generate a token, then copy and paste it below. "
            "The token is valid for 30 days."
        )
        explanation.setObjectName("FieldHint")
        explanation.setWordWrap(True)
        tab_layout.addWidget(explanation)

        self.open_token_page_button = QtWidgets.QPushButton("Open the Herma token page")
        page_button_layout = QtWidgets.QHBoxLayout()
        page_button_layout.addWidget(self.open_token_page_button)
        page_button_layout.addStretch()
        tab_layout.addLayout(page_button_layout)

        token_layout = self._build_form_layout()
        token_label = QtWidgets.QLabel("Herma token")
        token_label.setObjectName("FieldLabel")
        self.token_edit = QtWidgets.QLineEdit()
        self.token_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.token_edit.setMinimumWidth(300)
        self.token_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.token_edit.setPlaceholderText("Paste your Herma token")
        token_label.setBuddy(self.token_edit)
        token_layout.addRow(token_label, self.token_edit)
        tab_layout.addLayout(token_layout)
        tab_layout.addStretch()
        return tab

    def get_login_mode(self) -> str:
        if self.mode_tabs.currentIndex() == 1:
            return LOGIN_MODE_TOKEN
        return LOGIN_MODE_PASSWORD

    def set_login_mode(self, login_mode: str):
        self.mode_tabs.setCurrentIndex(1 if login_mode == LOGIN_MODE_TOKEN else 0)
        self._validate_credentials()

    def get_credentials(self):
        return self.email_edit.text(), self.password_edit.text()

    def get_login_data(self):
        return (
            self.environment_select.currentData(),
            self.email_edit.text(),
            self.password_edit.text(),
        )

    def get_token_login_data(self):
        return self.environment_select.currentData(), self.token_edit.text()

    def get_herma_token_url(self) -> str:
        selected_config = resolve_config(
            self.config, self.environment_select.currentData()
        )
        return get_herma_token_url(selected_config["euphrosyne"]["url"])

    def open_herma_token_page(self):
        QDesktopServices.openUrl(QUrl(self.get_herma_token_url()))

    def _validate_credentials(self, *_args):
        if self.get_login_mode() == LOGIN_MODE_TOKEN:
            self.ok_button.setEnabled(bool(self.token_edit.text().strip()))
            return
        self.ok_button.setEnabled(
            bool(self.email_edit.text().strip() and self.password_edit.text())
        )
