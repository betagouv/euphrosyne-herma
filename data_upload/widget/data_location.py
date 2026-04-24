from pathlib import Path

from PySide6.QtCore import QDir, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QVBoxLayout,
)


class DataLocationInputLayout(QVBoxLayout):
    folder_selected = Signal(str)
    selected_folder: str | None = None

    def __init__(self):
        super().__init__()
        self.setSpacing(6)
        title = QLabel()
        title.setText("Data folder location")
        title.setObjectName("FieldLabel")
        self.addWidget(title)

        self.data_path_box = QLineEdit()
        self.data_path_box.setPlaceholderText("Run data folder path")

        self.browse_button = QPushButton("Browse")
        self.browse_button.setIcon(
            QApplication.style().standardIcon(QStyle.SP_DirOpenIcon)
        )
        self.browse_button.clicked.connect(self.on_path_click)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        input_layout.addWidget(self.data_path_box, 1)
        input_layout.addWidget(self.browse_button)
        self.addLayout(input_layout)

    @property
    def data_folder(self) -> str | None:
        return self.data_path_box.text() or None

    @property
    def has_valid_data_folder(self) -> bool:
        folder = self.data_folder
        return bool(folder and Path(folder).is_dir())

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
