"""Figma 화면과 공유하는 PySide6 visual token과 QSS."""

COLORS = {
    "background": "#F5F7FA",
    "sidebar": "#0F2740",
    "sidebar_active": "#23496D",
    "sidebar_text": "#D5DEE8",
    "primary": "#2F6FED",
    "text": "#1F2937",
    "secondary": "#6B7280",
    "border": "#D8DEE8",
    "table_header": "#EEF2F6",
    "warning": "#A86800",
}

# Sidebar를 제외한 실제 content viewport 기준이다. 검색 폼만 폭에 따라
# wide/compact/narrow로 재배치하고 결과 workspace는 항상 수평 관계를 유지한다.
SEARCH_REFLOW_BREAKPOINT = 1080
SEARCH_NARROW_BREAKPOINT = 780
COMPACT_DETAIL_BREAKPOINT = 900
RESULT_WORKSPACE_MIN_WIDTH = 1040
CHARACTERISTIC_COLUMN_WIDTHS = (280, 150, 80, 240, 140)
QC_COLUMN_WIDTHS = (180, 100, 140, 480)
HISTORY_COLUMN_WIDTHS = (120, 70, 140, 80, 110, 180, 360)

STYLESHEET = """
QWidget { background: #F5F7FA; color: #1F2937;
  font-family: "Segoe UI", "Malgun Gothic"; font-size: 13px; }
QLabel#pageTitle { color: #1F2937; font-size: 25px; font-weight: 700; }
QLabel#pageSubtitle, QLabel#secondaryText { color: #6B7280; font-size: 12px; }
QLabel#sectionTitle { color: #1F2937; font-size: 15px; font-weight: 600; }
QLabel#fieldLabel { color: #6B7280; font-size: 12px; }
QLabel#fieldValue { color: #1F2937; font-size: 13px; font-weight: 500; }
QLabel#homeMetricLabel { color: #6B7280; font-size: 12px; font-weight: 600; }
QLabel#homeMetricValue { color: #1F2937; font-size: 21px; font-weight: 700; }
QLabel#brandAgency { color: white; font-size: 14px; font-weight: 700; }
QLabel#brandTitle { color: white; font-size: 16px; font-weight: 600; }
QLabel#navSection { color: #91A4B8; font-size: 11px; font-weight: 600;
  background: transparent; padding: 10px 12px 3px 12px; }
QLabel#errorText { color: #A33A32; }
QLabel#warningText { color: #A86800; }
QLabel#emptyState { color: #6B7280; background: white; border: 1px solid #D8DEE8;
  border-radius: 6px; padding: 28px; }
QWidget#sidebar { background: #0F2740; }
QWidget#sidebar QLabel, QWidget#sidebar QPushButton { background: transparent; }
QWidget#topbar { background: white; border-bottom: 1px solid #D8DEE8; }
QScrollArea#detailScrollArea, QScrollArea#detailScrollArea > QWidget > QWidget,
QWidget#detailContent { background: #F5F7FA; border: 0; }
QScrollArea#listScrollArea, QScrollArea#listScrollArea > QWidget > QWidget,
QWidget#listContent { background: #F5F7FA; border: 0; }
QScrollArea#myPageScrollArea, QScrollArea#myPageScrollArea > QWidget > QWidget,
QWidget#myPageContent { background: #F5F7FA; border: 0; }
QScrollArea#homeScrollArea, QScrollArea#homeScrollArea > QWidget > QWidget,
QWidget#homeContent { background: #F5F7FA; border: 0; }
QScrollArea#importScrollArea, QScrollArea#importScrollArea > QWidget > QWidget,
QWidget#importContent { background: #F5F7FA; border: 0; }
QLabel#databaseState { color: #4B5563; background: transparent; }
QLabel#databaseDot { color: #2F8A59; background: transparent; font-size: 16px; }
QFrame#card, QGroupBox { background: white; border: 1px solid #D8DEE8; border-radius: 6px; }
QGroupBox { font-weight: 600; padding-top: 16px; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QLineEdit, QComboBox { background: white; border: 1px solid #D8DEE8;
  border-radius: 5px; padding: 7px 10px; min-height: 20px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #2F6FED; }
QPushButton { background: white; border: 1px solid #D8DEE8;
  border-radius: 5px; padding: 7px 13px; min-height: 20px; }
QPushButton:hover { border-color: #2F6FED; }
QPushButton:disabled { color: #9CA3AF; background: #EEF2F6; }
QPushButton#primaryButton { color: white; background: #2F6FED;
  border-color: #2F6FED; font-weight: 600; }
QPushButton#compactButton { padding: 4px 9px; min-height: 18px; }
QPushButton#topbarUserButton { background: transparent; border: 1px solid transparent;
  padding: 0; min-height: 36px; }
QPushButton#topbarUserButton:hover, QPushButton#topbarUserButton:focus {
  background: #F5F7FA; border-color: #D8DEE8; }
QPushButton#navSelected, QPushButton#navButton { color: #D5DEE8; border: 0;
  border-radius: 4px; padding: 6px 12px 6px 18px;
  min-height: 20px; text-align: left; }
QPushButton#navSelected { color: white; background: #23496D; font-weight: 600;
  border-left: 3px solid #6EA2FF; }
QPushButton#navButton:hover { background: #173753; }
QTableView, QTableWidget { background: white; alternate-background-color: #FBFCFD;
  border: 1px solid #D8DEE8; gridline-color: #EDF0F4;
  selection-background-color: #EDF3FF; selection-color: #1F2937; }
QHeaderView::section { background: #EEF2F6; color: #1F2937; border: 0;
  border-right: 1px solid #E2E7EE; border-bottom: 1px solid #D8DEE8;
  padding: 9px 10px; font-size: 12px; font-weight: 600; }
QTabBar::tab { background: transparent; color: #6B7280; border: 0;
  border-bottom: 2px solid transparent; padding: 9px 16px; min-width: 90px; }
QTabBar::tab:selected { color: #2F6FED; border-bottom-color: #2F6FED; font-weight: 600; }
QTabBar::tab:hover { color: #1F2937; background: #F1F4F8; }
QTabWidget::pane { background: white; border: 1px solid #D8DEE8; border-radius: 5px; }
QLabel[statusKind="error"] { color: #9F2D27; background: #FDECEC; border: 1px solid #EAC1BE; }
QLabel[statusKind="warning"] { color: #8A5800; background: #FFF5DD; border: 1px solid #E8D19C; }
QLabel[statusKind="clear"] { color: #28704B; background: #EAF5EF; border: 1px solid #BEDDCA; }
QLabel[statusKind="current"] { color: #285FC0; background: #EAF1FF; border: 1px solid #C6D6F5; }
QLabel[statusKind="unassigned"] { color: #5F6875; background: #F1F3F5; border: 1px solid #D8DEE8; }
QLabel[statusKind="inconsistent"] { color: #9A4B12; background: #FFF0E6;
  border: 1px solid #E9C6AA; }
QLabel[statusKind="neutral"] { color: #4B5563; background: #F1F3F5; border: 1px solid #D8DEE8; }
QLabel[statusKind] { border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600; }
"""
