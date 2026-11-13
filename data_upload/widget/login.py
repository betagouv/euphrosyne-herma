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
            "Herma logs in with a Herma token generated on Euphrosyne."
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

        self._build_token_section(layout)

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
        self.token_edit.textChanged.connect(self._validate_credentials)
        self.open_token_page_button.clicked.connect(self.open_herma_token_page)

    @staticmethod
    def _build_form_layout() -> QtWidgets.QFormLayout:
        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(14)
        return form_layout

    def _build_token_section(self, layout: QtWidgets.QVBoxLayout):
        explanation = QtWidgets.QLabel(
            "Open the Herma token page on Euphrosyne and log in there "
            "(administrators use two-factor authentication). Generate a token, "
            "copy it and paste it below. The token is valid for 30 days."
        )
        explanation.setObjectName("FieldHint")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.open_token_page_button = QtWidgets.QPushButton("Open the Herma token page")
        page_button_layout = QtWidgets.QHBoxLayout()
        page_button_layout.addWidget(self.open_token_page_button)
        page_button_layout.addStretch()
        layout.addLayout(page_button_layout)

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
        layout.addLayout(token_layout)

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
        self.ok_button.setEnabled(bool(self.token_edit.text().strip()))
