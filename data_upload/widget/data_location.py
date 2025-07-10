from PySide6.QtCore import QDir, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QLineEdit,
    QStyle,
    QVBoxLayout,
)


class DataLocationInputLayout(QVBoxLayout):
    folder_selected = Signal(str)
    selected_folder: str | None = None

    def __init__(self):
        super().__init__()
        title = QLabel()
        title.setText("Data folder location")
        self.addWidget(title)

        self.data_path_box = QLineEdit()
        self.data_path_box.setPlaceholderText("Run data folder path")
        self.data_path_box.addAction(
            QApplication.style().standardIcon(QStyle.SP_DirOpenIcon),
            QLineEdit.TrailingPosition,
        ).triggered.connect(self.on_path_click)
        self.addWidget(self.data_path_box)

    @property
    def data_folder(self) -> str | None:
        return self.data_path_box.text() or None

    @Slot()
    def on_path_click(self):
        folder = QFileDialog.getExistingDirectory(
            caption="Open data folder",
            dir=QDir.homePath(),
        )
        if folder:
            self.data_path_box.setText(folder)
            self.selected_folder = folder
            self.folder_selected.emit(folder)
