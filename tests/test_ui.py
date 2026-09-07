"""Qt smoke tests: optional configuration, invalidation, upload and export paths."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtGui import QFontDatabase, QPixmap, QWheelEvent
from PySide6.QtCore import Qt, QPoint, QPointF
from UI.main_window import MainWindow
from core.workflow import TopologySession
from test_workflow import CONNECTIONS, POSITIONS


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # Windows offscreen platform does not enumerate system fonts.
        for name in ('segoeui.ttf', 'segoeuil.ttf', 'segoeuib.ttf'):
            path = Path('C:/Windows/Fonts') / name
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))

    def setUp(self):
        self.window = MainWindow()
        self.window.resize(1240, 860)
        self.errors = []
        self.window.error = self.errors.append
        self.window.show()
        self.app.processEvents()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self.window.close)

    def load_sample(self):
        session = TopologySession()
        folder = Path(self.folder.name)
        (folder / 'conexiones.csv').write_text(CONNECTIONS, encoding='utf-8')
        (folder / 'pos.csv').write_text(POSITIONS, encoding='utf-8')
        session.load(folder / 'conexiones.csv', folder / 'pos.csv')
        original_generator = session.generator
        def generator(configured=False):
            result = original_generator(configured)
            result.data_dir = folder / 'data'
            return result
        session.generator = generator
        self.window.loaded(session)
        self.app.processEvents()

    def test_initial_and_optional_flow(self):
        self.assertEqual(self.window.tabs.count(), 3)
        self.assertFalse(self.window.tabs.isTabEnabled(1))
        self.assertFalse(self.window.tabs.isTabEnabled(2))
        self.load_sample()
        self.window.skip_config()
        self.assertEqual(self.window.tabs.currentIndex(), 2)
        self.assertFalse(self.window.include_config.isChecked())
        destination = str(Path(self.folder.name) / 'bare.pkt')
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(destination, '')):
            self.window.generate()
        self.assertTrue(Path(destination).is_file())
        self.assertEqual(self.errors, [])

    def test_configure_edit_invalidates_then_export(self):
        self.load_sample()
        self.window.branch_table.cellWidget(0, 2).setValue(2)
        self.window.apply_config()
        self.assertEqual(self.errors, [])
        self.assertTrue(self.window.include_config.isChecked())
        self.window.segment_table.item(0, 2).setText('192.168.10.0/24')
        self.assertIsNone(self.window.session.configured)
        self.assertFalse(self.window.include_config.isEnabled())
        self.window.apply_config()
        self.assertEqual(self.errors, [])
        export_dir = Path(self.folder.name) / 'export'
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(export_dir)):
            self.window.export_md()
        self.assertEqual({p.name for p in export_dir.iterdir()}, {'cisco.md', 'pcs.md'})

    def test_manual_ips_expand_segment_count_and_table(self):
        self.load_sample()
        for row in range(self.window.ip_table.rowCount()):
            name = self.window.ip_table.item(row, 0).text()
            if name in ('PC1', 'PC2'):
                ip = '192.168.10.10' if name == 'PC1' else '192.168.20.10'
                self.window.ip_table.item(row, 1).setText(ip)
                self.window.ip_table.item(row, 2).setText('24')
        self.window.apply_config()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.window.branch_table.cellWidget(0, 2).value(), 2)
        self.assertEqual(self.window.segment_table.rowCount(), 3)
        self.assertEqual(self.window.segment_table.item(1, 2).text(), '192.168.20.0/24')
        self.assertTrue(self.window.include_config.isChecked())
        self.window.apply_config()
        self.assertEqual(self.errors, [])

    def wheel(self, target, delta):
        position = QPoint(10, 10)
        event = QWheelEvent(QPointF(position), QPointF(target.mapToGlobal(position)),
                            QPoint(), QPoint(0, delta), Qt.NoButton, Qt.NoModifier,
                            Qt.NoScrollPhase, False)
        QApplication.sendEvent(target, event)
        return event

    def test_table_scroll_stays_inside_at_both_boundaries(self):
        self.load_sample()
        self.window.tabs.setCurrentIndex(1)
        table = self.window.branch_table
        table.setRowCount(60)
        self.app.processEvents()
        outer = self.window.tabs.widget(1).verticalScrollBar()
        inner = table.verticalScrollBar()
        self.assertGreater(inner.maximum(), 0)
        for boundary, delta in ((inner.maximum(), -120), (0, 120)):
            outer.setValue(outer.maximum() // 2)
            previous = outer.value()
            inner.setValue(boundary)
            for target in (table.viewport(), inner):
                event = self.wheel(target, delta)
                self.assertTrue(event.isAccepted())
                self.assertEqual(outer.value(), previous)
                self.assertEqual(inner.value(), boundary)
        inner.setValue(0)
        self.wheel(table.viewport(), -120)
        self.assertGreater(inner.value(), 0)
        outer.setValue(0)
        self.wheel(self.window.tabs.widget(1).viewport(), -120)
        self.assertGreater(outer.value(), 0)

    def test_wheel_does_not_edit_unfocused_controls(self):
        self.load_sample()
        self.window.tabs.setCurrentIndex(1)
        self.window.tabs.setFocus()
        for control in (self.window.branch_table.cellWidget(0, 2), self.window.router_table.cellWidget(0, 1)):
            self.assertFalse(control.hasFocus())
            self.assertEqual(control.focusPolicy(), Qt.StrongFocus)
            event = self.wheel(control, 120)
            self.assertFalse(event.isAccepted())
        self.assertEqual(self.window.branch_table.cellWidget(0, 2).value(), 1)
        self.assertEqual(self.window.router_table.cellWidget(0, 1).currentText(), 'Sin protocolo')

    def test_invalid_inputs_block_configuration(self):
        self.load_sample()
        self.window.ip_table.item(0, 1).setText('192.168.1.1')
        self.window.apply_config()
        self.assertTrue(self.errors)
        self.assertFalse(self.window.include_config.isEnabled())

    def test_new_image_resets_previous_results(self):
        self.load_sample()
        self.window.apply_config()
        path = str(Path('imagenes/topologia.png').resolve())
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(path, '')):
            self.window.pick_image()
        self.assertIsNone(self.window.session.base)
        self.assertFalse(self.window.tabs.isTabEnabled(2))
        self.assertFalse(self.window.include_config.isEnabled())

    def test_render_screens(self):
        folder = Path('artifacts')
        folder.mkdir(exist_ok=True)
        self.window.grab().save(str(folder / '01-cargar-imagen.png'))
        self.load_sample()
        self.window.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.window.grab().save(str(folder / '02-configurar.png'))
        self.window.apply_config()
        self.window.tabs.setCurrentIndex(2)
        self.app.processEvents()
        self.window.grab().save(str(folder / '03-crear-archivo.png'))
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
