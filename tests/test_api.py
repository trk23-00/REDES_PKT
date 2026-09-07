import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from PIL import Image
from api_gemini.procesador import procesar_topologia_red
from UI.main_window import AnalysisWorker, DATA_DIR
from test_workflow import CONNECTIONS, POSITIONS

RESPONSE = f'### ARCHIVO: pos.csv\n```csv\n{POSITIONS}\n```\n### ARCHIVO: conexiones.csv\n```csv\n{CONNECTIONS}```'


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)
        self.image = self.path / 'source.png'
        Image.new('RGB', (20, 20), 'white').save(self.image)

    def test_missing_key(self):
        with patch.dict(os.environ, {}, clear=True), patch('api_gemini.procesador.load_dotenv'), self.assertRaisesRegex(ValueError, 'GEMINI_API_KEY'):
            procesar_topologia_red(self.image, self.path / 'data')

    def test_current_api_writes_csv_and_worker_reads_same_data_folder(self):
        client = MagicMock()
        def response(**kwargs):
            kwargs['contents'][0].load()
            return SimpleNamespace(text=RESPONSE)
        client.models.generate_content.side_effect = response
        destination = self.path / 'data'
        worker = AnalysisWorker(str(self.image))
        results, errors = [], []
        worker.ready.connect(results.append)
        worker.failed.connect(errors.append)
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-test-key'}), patch('api_gemini.procesador.genai.Client', return_value=client), patch('api_gemini.procesador.load_dotenv'), patch('UI.main_window.DATA_DIR', destination):
            worker.run()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].base.dic_device_objeto), 7)
        self.assertEqual({p.name for p in destination.iterdir()}, {'conexiones.csv', 'pos.csv'})
        self.assertEqual(DATA_DIR, Path(__file__).resolve().parents[1] / 'data')

    def test_partial_response_cannot_use_previous_csv(self):
        destination = self.path / 'data'
        destination.mkdir()
        (destination / 'conexiones.csv').write_text(CONNECTIONS, encoding='utf-8')
        (destination / 'pos.csv').write_text(POSITIONS, encoding='utf-8')
        worker = AnalysisWorker(str(self.image))
        results, errors = [], []
        worker.ready.connect(results.append)
        worker.failed.connect(errors.append)
        with patch('UI.main_window.DATA_DIR', destination), patch('api_gemini.procesador.procesar_topologia_red', return_value=[str(destination / 'pos.csv')]):
            worker.run()
        self.assertEqual(results, [])
        self.assertIn('no generó', errors[0])
