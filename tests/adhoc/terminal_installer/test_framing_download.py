# Installer regression tests; outside the Pi runtime requirements baseline.
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('model_download_test', ROOT/'build_tools/linux/download-framing-model.py')
download = importlib.util.module_from_spec(spec); spec.loader.exec_module(download)


class FramingModelTests(unittest.TestCase):
    def test_checksum_before_replace_and_no_download_when_already_installed(self):
        data = b'fixture model'
        with tempfile.TemporaryDirectory() as directory, patch.object(download, 'SHA256', hashlib.sha256(data).hexdigest()):
            path = Path(directory)/'model.tflite'; path.write_bytes(b'previous')
            with patch.object(download.urllib.request, 'urlopen', return_value=io.BytesIO(b'invalid')):
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    download.download(path)
            self.assertEqual(path.read_bytes(), b'previous')
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = data
            with patch.object(download.urllib.request, 'urlopen', return_value=response) as network:
                download.download(path)
            network.assert_called_once_with(download.URL, timeout=60)
            response.read.assert_called_once_with(8 * 1024 * 1024)
            self.assertEqual(path.read_bytes(), data)
            with patch.object(download.urllib.request, 'urlopen') as network:
                download.download(path); network.assert_not_called()
