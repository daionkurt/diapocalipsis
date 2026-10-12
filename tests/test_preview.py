from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from streamlit.testing.v1 import AppTest
import storage
from document_preview import office_text, text_contents


class PreviewTest(unittest.TestCase):
    def test_word_and_slides_text_is_extracted_in_order(self):
        buf = BytesIO()
        with zipfile.ZipFile(buf, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Una teoría</w:t></w:r></w:p></w:document>')
            for number in (10, 2, 1):
                archive.writestr(f'ppt/slides/slide{number}.xml', f'<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>Teoría {number}</a:t></a:r></a:p>')
        self.assertEqual(office_text('file.docx', buf.getvalue()), [('Documento', 'Una teoría')])
        self.assertEqual([title for title, _ in office_text('file.pptx', buf.getvalue())], ['Diapositiva 1', 'Diapositiva 2', 'Diapositiva 10'])

    def test_text_encodings_are_displayed(self):
        for encoding in ('utf-8', 'utf-16', 'cp1252'):
            with self.subTest(encoding=encoding):
                self.assertEqual(text_contents('Una aparición'.encode(encoding)), 'Una aparición')

    def test_private_preview_requires_login_and_download_is_available(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            'STORAGE_BACKEND': 'sqlite', 'DIAPOCALIPSIS_DATA_DIR': folder,
            'ADMIN_PASSWORD': 'test-only', 'SUPABASE_URL': '', 'SUPABASE_SECRET_KEY': '',
        }):
            contents = b'%PDF-1.4\ntest preview fixture'
            token = storage.register('Ana', 'ana@example.com', 'La Luna', ('pruebas.pdf', contents), now=storage.DEADLINE.replace(day=22))
            path = str(Path(__file__).resolve().parents[1] / 'app.py')
            with patch('streamlit.pdf') as viewer:
                app = AppTest.from_file(path).run()
                viewer.assert_not_called()
                app.session_state['guest_access'] = (1, token, 'ana@example.com')
                app.run()
                self.assertFalse(app.exception)
                viewer.assert_called_once_with(contents, height=650, key='guest_pdf_1')
                labels = [item.proto.label for item in app.get('download_button')]
                self.assertIn('Descargar mi archivo', labels)


if __name__ == '__main__':
    unittest.main()
