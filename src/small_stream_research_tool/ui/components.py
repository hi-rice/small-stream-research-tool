"""조회 화면에서 공유하는 상태 badge와 table delegate."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QStyledItemDelegate

BADGE_KIND = {
    "오류": "error",
    "확인 필요": "warning",
    "활성 문제 없음": "clear",
    "현재 사용값 있음": "current",
    "현재 사용값 미지정": "unassigned",
    "현재값 연결 확인 필요": "inconsistent",
}


class StatusBadge(QLabel):
    def __init__(self, text="—", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(self.sizePolicy().Policy.Maximum, self.sizePolicy().Policy.Fixed)
        self.set_status(text)

    def set_status(self, text):
        self.setText(text)
        self.setProperty("statusKind", BADGE_KIND.get(text, "neutral"))
        self.style().unpolish(self)
        self.style().polish(self)


class StatusBadgeDelegate(QStyledItemDelegate):
    """표의 상태 text를 의미가 보존되는 muted badge로 그린다."""

    PALETTE = {
        "error": ("#FDECEC", "#9F2D27", "#EAC1BE"),
        "warning": ("#FFF5DD", "#8A5800", "#E8D19C"),
        "clear": ("#EAF5EF", "#28704B", "#BEDDCA"),
        "current": ("#EAF1FF", "#285FC0", "#C6D6F5"),
        "unassigned": ("#F1F3F5", "#5F6875", "#D8DEE8"),
        "inconsistent": ("#FFF0E6", "#9A4B12", "#E9C6AA"),
        "neutral": ("#F1F3F5", "#4B5563", "#D8DEE8"),
    }

    def paint(self, painter, option, index):
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        kind = BADGE_KIND.get(text, "neutral")
        background, foreground, border = self.PALETTE[kind]
        painter.save()
        if option.state & option.state.State_Selected:
            painter.fillRect(option.rect, QColor("#EDF3FF"))
        metrics = option.fontMetrics
        width = min(option.rect.width() - 16, metrics.horizontalAdvance(text) + 22)
        rect = QRectF(
            option.rect.x() + 8,
            option.rect.center().y() - 12,
            max(width, 36),
            24,
        )
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(border)))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(QColor(foreground))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
