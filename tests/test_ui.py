"""Qt smoke tests: optional configuration, invalidation, upload and export paths."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtGui import QFontDatabase, QPixmap
from UI.main_window import MainWindow
from core.workflow import TopologySession


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
        session.load('data/conexiones.csv', 'data/pos.csv')
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
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=self.folder.name):
            self.window.export_md()
        self.assertEqual({p.name for p in Path(self.folder.name).iterdir()}, {'cisco.md', 'pcs.md'})

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
