QSS = """
QWidget { color: #292d2d; font-family: "Segoe UI"; font-size: 13px; }
QMainWindow, QWidget#Background { background: #f4f5f4; }
QFrame#Sidebar { background: #272a29; border-radius: 20px; }
QFrame#Sidebar QLabel { color: #f3f5f4; background: transparent; }
QLabel#Brand { font-family: "Segoe UI Light"; font-size: 33px; font-weight: 300; }
QLabel#Title { font-family: "Segoe UI Light"; font-size: 30px; font-weight: 300; }
QLabel#Kicker { color: #278675; font-size: 11px; font-weight: 600; }
QLabel#Hint { color: #66716f; }
QFrame#Card { background: white; border: 1px solid #e2e7e5; border-radius: 18px; }
QLabel#Preview { background: #edf1ef; border: 1px dashed #a6c6bf; border-radius: 14px; color: #536d66; }
QPushButton { background: #e7eeeb; border: 1px solid #d7e1dd; border-radius: 9px; padding: 11px 17px; font-weight: 600; }
QPushButton:hover { background: #d7e8e2; border-color: #72b4a4; }
QPushButton#Primary { background: #4fae9c; border-color: #4fae9c; color: #112e27; }
QPushButton#Primary:hover { background: #6ac2b1; }
QPushButton#Coral { background: #ff7971; border-color: #ff7971; color: #3e201f; }
QPushButton:disabled { background: #e6e8e7; color: #89908e; border-color: #e6e8e7; }
QPushButton#Primary:disabled, QPushButton#Coral:disabled { background: #e6e8e7; color: #89908e; border-color: #e6e8e7; }
QTabWidget::pane { border: none; background: #f4f5f4; }
QTabBar::tab { padding: 14px 22px; margin-right: 8px; background: #e9eeeb; border-radius: 9px; color: #65716b; }
QTabBar::tab:selected { background: #d6ebe4; color: #216b59; }
QTabBar::tab:disabled { color: #a6adaa; }
QLineEdit, QSpinBox, QComboBox { background: white; border: 1px solid #cedbd5; border-radius: 7px; padding: 7px; min-height: 20px; selection-background-color: #acd8c8; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #4fae9c; }
QSpinBox#SegmentCount { padding: 0px 48px 0px 10px; min-height: 48px; }
QToolButton#SegmentStep { background: #e4f0eb; color: #216b59; border: 1px solid #c5dacf; border-radius: 4px; padding: 0px; }
QToolButton#SegmentStep:hover { background: #c9e5d9; }
QToolButton#SegmentStep:pressed { background: #a9d5c3; }
QToolButton#SegmentStep:disabled { color: #9caaa3; background: #f0f3f1; }
QTableWidget { background: white; alternate-background-color: #f6f8f7; border: 1px solid #dfe7e2; border-radius: 8px; gridline-color: #edf1ef; selection-background-color: #d6ebe4; selection-color: #253d34; }
QHeaderView::section { background: #edf3ef; border: none; padding: 9px; color: #496156; font-weight: 600; }
QCheckBox { spacing: 8px; padding: 4px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #eaf0ec; width: 14px; margin: 0px; border-radius: 7px; }
QScrollBar:horizontal { background: #eaf0ec; height: 14px; margin: 0px; border-radius: 7px; }
QScrollBar::handle:vertical { background: #a2b9af; min-height: 36px; border-radius: 7px; }
QScrollBar::handle:horizontal { background: #a2b9af; min-width: 36px; border-radius: 7px; }
QScrollBar::handle:hover { background: #70a58f; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QProgressBar { background: #e1e9e5; border: none; border-radius: 4px; max-height: 8px; }
QProgressBar::chunk { background: #4fae9c; border-radius: 4px; }
QStatusBar { background: #e8eeea; color: #52695d; }
QToolTip { background: #272a29; color: white; border: none; padding: 6px; }
"""
