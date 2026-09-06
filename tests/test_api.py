import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image
from api_gemini.procesador import procesar_topologia_red

RESPONSE = '### ARCHIVO: pos.csv\n```csv\nPC1,100,100\n```\n### ARCHIVO: conexiones.csv\n```csv\nPC1:pc,c,None:None\n```'


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)
        self.image = self.path / 'source.png'
        Image.new('RGB', (20, 20), 'white').save(self.image)

    def test_missing_key(self):
        with patch.dict(os.environ, {}, clear=True), patch('api_gemini.procesador.load_dotenv'), self.assertRaisesRegex(ValueError, 'GEMINI_API_KEY'):
            procesar_topologia_red(self.image, self.path / 'output')

    def test_response_validated_before_writing(self):
        client = MagicMock()
        client.__enter__.return_value.models.generate_content.return_value.text = RESPONSE
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-test-key', 'GEMINI_MODEL': 'test-model'}), patch('api_gemini.procesador.genai.Client', return_value=client), patch('api_gemini.procesador.load_dotenv'):
            files = procesar_topologia_red(self.image, self.path / 'output')
        self.assertEqual({Path(p).name for p in files}, {'conexiones.csv', 'pos.csv'})
        self.assertTrue(all(Path(p).exists() for p in files))
        call = client.__enter__.return_value.models.generate_content.call_args
        self.assertEqual(call.kwargs['model'], 'test-model')

    def test_malformed_api_output_does_not_overwrite(self):
        client = MagicMock()
        client.__enter__.return_value.models.generate_content.return_value.text = RESPONSE.replace('pos.csv', '../unsafe.csv')
        output = self.path / 'output'
        output.mkdir()
        sentinel = output / 'pos.csv'
        sentinel.write_text('previous', encoding='utf-8')
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-test-key'}), patch('api_gemini.procesador.genai.Client', return_value=client), patch('api_gemini.procesador.load_dotenv'), self.assertRaises(ValueError):
            procesar_topologia_red(self.image, output)
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'previous')
        self.assertFalse((self.path / 'unsafe.csv').exists())
