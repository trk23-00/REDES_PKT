"""Keep wheel gestures inside their table, including at scroll boundaries."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QScrollBar, QSpinBox, QComboBox


class ContainedScrollBar(QScrollBar):
    def wheelEvent(self, event):
        super().wheelEvent(event)
        event.accept()


class ContainedTable(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setVerticalScrollBar(ContainedScrollBar(Qt.Vertical, self))
        self.setHorizontalScrollBar(ContainedScrollBar(Qt.Horizontal, self))

    def wheelEvent(self, event):
        super().wheelEvent(event)
        # Qt normally ignores wheel events when the scrollbar reaches its limit,
        # which makes the enclosing configuration page jump unexpectedly.
        event.accept()


class FocusWheelMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
            event.accept()
        else:
            # Scroll the containing table without changing the unfocused value.
            event.ignore()


class FocusSpinBox(FocusWheelMixin, QSpinBox):
    pass


class FocusComboBox(FocusWheelMixin, QComboBox):
    pass
