import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import storage


class DownloadTest(unittest.TestCase):
    def test_private_download_requires_login_and_has_no_preview(self):
        for filename, contents in [('pruebas.pdf', b'%PDF-1.4\nprivate preview fixture'),
                                   ('secreto.txt', b'private-content-do-not-render')]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
                'STORAGE_BACKEND': 'sqlite', 'DIAPOCALIPSIS_DATA_DIR': folder,
                'ADMIN_PASSWORD': 'test-only', 'SUPABASE_URL': '', 'SUPABASE_SECRET_KEY': '',
            }):
                token = storage.register('Ana', 'ana@example.com', 'La Luna', (filename, contents), now=storage.DEADLINE.replace(day=22))
                path = str(Path(__file__).resolve().parents[1] / 'app.py')
                with patch('streamlit.pdf') as viewer:
                    app = AppTest.from_file(path).run()
                    self.assertNotIn('Descargar mi archivo', [i.proto.label for i in app.get('download_button')])
                    app.session_state['guest_access'] = (1, token, 'ana@example.com')
                    app.session_state['navigation'] = '02 / Mi expediente'
                    app.run()
                    self.assertFalse(app.exception)
                    viewer.assert_not_called()
                    self.assertIn('Descargar mi archivo', [i.proto.label for i in app.get('download_button')])
                    self.assertFalse(any(contents.decode() in i.value for i in app.code))


if __name__ == '__main__':
    unittest.main()
