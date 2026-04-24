from PySide6.QtWidgets import QApplication

APP_STYLESHEET = """
QWidget {
    background: #f7f5f1;
    color: #2f2823;
    font-size: 13px;
}

QLabel {
    background: transparent;
}

QDialog,
QWidget#DataUploadWidget {
    background: #f7f5f1;
}

QLabel#AppTitle,
QLabel#DialogTitle {
    color: #211b17;
    font-size: 22px;
    font-weight: 700;
}

QLabel#DialogTitle {
    font-size: 20px;
}

QLabel#SectionTitle {
    color: #211b17;
    font-size: 16px;
    font-weight: 700;
}

QLabel#Subtitle,
QLabel#FieldHint {
    color: #6f6258;
}

QLabel#FieldLabel {
    color: #4b4038;
    font-weight: 600;
}

QFrame#Panel,
QFrame#StatusPanel {
    background: #fffdf9;
    border: 1px solid #ded5ca;
    border-radius: 8px;
}

QLabel#StatusTitle {
    color: #211b17;
    font-size: 14px;
    font-weight: 700;
}

QLabel#StatusMessage {
    color: #5e5148;
}

QLineEdit,
QComboBox,
QTextEdit {
    background: #ffffff;
    border: 1px solid #cfc6ba;
    border-radius: 6px;
    padding: 7px 9px;
    selection-background-color: #c78b38;
}

QLineEdit:focus,
QComboBox:focus,
QTextEdit:focus {
    border: 1px solid #9c6420;
}

QLineEdit:disabled,
QComboBox:disabled,
QTextEdit:disabled {
    background: #eee9e2;
    color: #8a7d71;
}

QTextEdit#TransferLog {
    background: #211b17;
    border: 1px solid #3f342d;
    color: #f8efe4;
    font-family: Menlo, Consolas, monospace;
    font-size: 12px;
}

QPushButton {
    background: #efe8dd;
    border: 1px solid #cfc6ba;
    border-radius: 6px;
    color: #2f2823;
    font-weight: 600;
    min-height: 34px;
    padding: 7px 14px;
}

QPushButton:hover {
    background: #e4dacd;
}

QPushButton:pressed {
    background: #d7cabb;
}

QPushButton:disabled {
    background: #e8e2da;
    border-color: #d8d0c7;
    color: #998d82;
}

QPushButton#PrimaryButton {
    background: #8f5d25;
    border-color: #8f5d25;
    color: #ffffff;
}

QPushButton#PrimaryButton:hover {
    background: #764b1b;
}

QPushButton#PrimaryButton:disabled {
    background: #cbb9a6;
    border-color: #cbb9a6;
    color: #fff7ee;
}

QPushButton#DangerButton {
    background: transparent;
    border-color: #d8b8b8;
    color: #a62d2d;
}

QPushButton#DangerButton:hover {
    background: #f8eaea;
}

QProgressBar {
    background: #eee6dc;
    border: 1px solid #d7cec2;
    border-radius: 5px;
    height: 8px;
    text-align: center;
}

QProgressBar::chunk {
    background: #c78b38;
    border-radius: 4px;
}
"""


def apply_app_theme(app: QApplication) -> None:
    app.setStyleSheet(APP_STYLESHEET)
