"""연구업무용 최소 공통 Qt 스타일."""

STYLESHEET = """
QWidget { background: #f5f7f9; color: #203044; font-size: 12pt; }
QLabel#pageTitle { color: #16334c; font-size: 21pt; font-weight: 700; }
QLabel#errorText { color: #a33a32; }
QLineEdit, QComboBox { background: white; border: 1px solid #c5d0d8;
  border-radius: 4px; padding: 8px; min-height: 22px; }
QLineEdit:focus, QComboBox:focus { border: 2px solid #197d84; }
QPushButton { background: white; border: 1px solid #b9c9d2;
  border-radius: 4px; padding: 8px 14px; min-height: 22px; }
QPushButton:hover { border-color: #197d84; }
QPushButton:disabled { color: #80909c; background: #e9edf0; }
QPushButton#primaryButton { color: white; background: #176e79; border-color: #176e79; }
QPushButton#navSelected { color: white; background: #20445f;
  border-color: #20445f; text-align: left; }
QPushButton#navButton { text-align: left; }
QTableView { background: white; alternate-background-color: #f0f5f7;
  border: 1px solid #d2dce3; gridline-color: #e4e9ed; selection-background-color: #d6edf0;
  selection-color: #16334c; }
QHeaderView::section { background: #e8eef2; color: #203b52; border: 0;
  border-right: 1px solid #d2dce3; padding: 9px; font-weight: 600; }
"""
