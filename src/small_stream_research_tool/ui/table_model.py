"""조회 결과를 QTableView에 표시한다. SQL과 Service 호출은 없다."""

from PySide6.QtCore import QAbstractTableModel, Qt

from small_stream_research_tool.ui.presentation import HEADERS, display_row


class StreamListTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = ()

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self._rows)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return display_row(self._rows[index.row()])[index.column()]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def flags(self, index):
        return (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if index.isValid()
            else Qt.ItemFlag.NoItemFlags
        )

    def stream_code(self, row):
        return self._rows[row].stream_code
