from PySide6 import QtWidgets


class LoginDialog(QtWidgets.QDialog):
    def __init__(self, config):
        super().__init__()
        self.setWindowTitle("Login to Euphrosyne")

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("Email:"))
        self.email_edit = QtWidgets.QLineEdit()
        self.email_edit.setPlaceholderText("Enter your email")
        layout.addWidget(self.email_edit)

        layout.addWidget(QtWidgets.QLabel("Password:"))
        self.password_edit = QtWidgets.QLineEdit()
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password_edit.setPlaceholderText("Enter your password")
        layout.addWidget(self.password_edit)

        button_layout = QtWidgets.QHBoxLayout()
        self.ok_button = QtWidgets.QPushButton("OK")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def get_credentials(self):
        return self.email_edit.text(), self.password_edit.text()
