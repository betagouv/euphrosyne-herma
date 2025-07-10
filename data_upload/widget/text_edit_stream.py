from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit


class TextEditStream(QObject):
    write_signal = Signal(str)
    text_edit: QTextEdit | None = None

    def connect(self, text_edit: QTextEdit):
        """Connect the QTextEdit to this stream."""
        self.text_edit = text_edit
        self.write_signal.connect(self._append_text)

    def write(self, text):
        self.write_signal.emit(str(text))

    def flush(self):
        pass  # Needed for compatibility

    def _append_text(self, text):
        if not self.text_edit:
            raise ValueError("TextEdit must be connected to a stream before writing.")
        self.text_edit.moveCursor(QTextCursor.End)
        self.text_edit.insertPlainText(text)
