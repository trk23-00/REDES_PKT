import sys
from PySide6.QtWidgets import QApplication

from UI.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1240, 860)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
