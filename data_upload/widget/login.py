from PySide6 import QtWidgets
from PySide6.QtCore import Qt


class LoginDialog(QtWidgets.QDialog):
    def __init__(self, config):
        super().__init__()
        self.setWindowTitle("Login to Euphrosyne")
        self.setMinimumWidth(380)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QtWidgets.QLabel("Log in to Euphrosyne")
        title.setObjectName("DialogTitle")
        subtitle = QtWidgets.QLabel("Use your Euphrosyne credentials to continue.")
        subtitle.setObjectName("Subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(14)

        email_label = QtWidgets.QLabel("Email")
        email_label.setObjectName("FieldLabel")
        self.email_edit = QtWidgets.QLineEdit()
        self.email_edit.setPlaceholderText("name@example.com")
        email_label.setBuddy(self.email_edit)
        form_layout.addRow(email_label, self.email_edit)

        password_label = QtWidgets.QLabel("Password")
        password_label.setObjectName("FieldLabel")
        self.password_edit = QtWidgets.QLineEdit()
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password_edit.setPlaceholderText("Enter your password")
        password_label.setBuddy(self.password_edit)
        form_layout.addRow(password_label, self.password_edit)
        layout.addLayout(form_layout)

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

    def get_credentials(self):
        return self.email_edit.text(), self.password_edit.text()

    def _validate_credentials(self):
        self.ok_button.setEnabled(
            bool(self.email_edit.text().strip() and self.password_edit.text())
        )
