"""Keep wheel gestures inside their table, including at scroll boundaries."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QScrollBar, QSpinBox, QComboBox, QToolButton, QAbstractSpinBox


class ContainedScrollBar(QScrollBar):
    def wheelEvent(self, event):
        super().wheelEvent(event)
        event.accept()


class ContainedTable(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setVerticalScrollBar(ContainedScrollBar(Qt.Vertical, self))
        self.setHorizontalScrollBar(ContainedScrollBar(Qt.Horizontal, self))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

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
        # La rueda desplaza la tabla, nunca modifica el valor, incluso con foco.
        event.ignore()


class FocusSpinBox(FocusWheelMixin, QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName('SegmentCount')
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setMinimumHeight(48)
        self.up_button = self._step_button(Qt.UpArrow, 'Aumentar segmentos', 1)
        self.down_button = self._step_button(Qt.DownArrow, 'Reducir segmentos', -1)
        self.valueChanged.connect(self._update_buttons)
        self._update_buttons()
        self._position_buttons()

    def _step_button(self, arrow, description, direction):
        button = QToolButton(self)
        button.setObjectName('SegmentStep')
        button.setArrowType(arrow)
        button.setAccessibleName(description)
        button.setToolTip(description)
        button.setAutoRepeat(True)
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(lambda: self._step(direction))
        return button

    def _step(self, direction):
        self.setFocus(Qt.MouseFocusReason)
        self.stepBy(direction)

    def _update_buttons(self):
        self.up_button.setEnabled(self.value() < self.maximum())
        self.down_button.setEnabled(self.value() > self.minimum())

    def _position_buttons(self):
        width = 42
        height = self.height() - 2
        self.up_button.setGeometry(self.width() - width - 1, 1, width, height // 2)
        self.down_button.setGeometry(self.width() - width - 1, 1 + height // 2, width, height - height // 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_buttons()


class FocusComboBox(FocusWheelMixin, QComboBox):
    pass
