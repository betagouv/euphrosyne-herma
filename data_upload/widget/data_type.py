import enum

from PySide6 import QtWidgets
from PySide6.QtCore import Signal


class ExtractionType(enum.Enum):
    RAW_DATA = "raw data"
    PROCESSED_DATA = "processed data"


class DataTypeCheckboxesLayout(QtWidgets.QComboBox):
    selected = Signal(ExtractionType | None)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setPlaceholderText("Select data type")

        self.addItems([extraction.value for extraction in ExtractionType])
        self.setCurrentIndex(0)

        self.currentIndexChanged.connect(self.on_selection_changed)

    @property
    def selected_data_type(self) -> ExtractionType | None:
        selected_item = self.currentText()
        if not selected_item:
            return None
        return next(
            (
                extraction
                for extraction in ExtractionType
                if extraction.value == selected_item
            ),
            None,
        )

    def on_selection_changed(self):
        selected_type = self.selected_data_type
        self.selected.emit(selected_type)
