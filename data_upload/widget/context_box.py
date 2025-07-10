import sys

from PySide6.QtWidgets import QTextEdit

from data_upload.widget.text_edit_stream import TextEditStream


class ContextBox(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.stdout_stream = TextEditStream(self)
        sys.stdout = self.stdout_stream
        sys.stderr = self.stdout_stream
        self.setMinimumHeight(300)
