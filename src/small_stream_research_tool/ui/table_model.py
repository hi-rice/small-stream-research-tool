"""조회 결과를 QTableView에 표시한다. SQL과 Service 호출은 없다."""

from PySide6.QtCore import QAbstractTableModel, Qt

from small_stream_research_tool.ui.presentation import (
    CURRENT_TEXT,
    HEADERS,
    STATUS_TEXT,
    display_row,
    display_value,
)


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


class CharacteristicTableModel(QAbstractTableModel):
    HEADERS = ("항목", "현재 사용값", "단위", "데이터 상태", "연구 분류")

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
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        row = self._rows[index.row()]
        state = CURRENT_TEXT.get(row.current_use_status, "상태 확인 필요")
        if row.current_use_status == "VALID_CURRENT":
            state += " · " + STATUS_TEXT.get(row.qc_display_state, "상태 확인 필요")
        values = (
            row.standard_name,
            display_value(row.current_value),
            row.unit_display or "—",
            state,
            " · ".join(
                label
                for enabled, label in (
                    (row.representative_six, "대표 6"),
                    (row.focus_nine, "전국 분석 9"),
                )
                if enabled
            )
            or "—",
        )
        return values[index.column()]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        return (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if index.isValid()
            else Qt.ItemFlag.NoItemFlags
        )

    def row(self, index):
        return self._rows[index]
