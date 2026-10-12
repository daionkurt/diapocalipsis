from contextlib import closing
from datetime import timedelta
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest
import recovery
import storage

NOW = storage.DEADLINE.replace(day=12)


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'STORAGE_BACKEND': 'sqlite', 'DIAPOCALIPSIS_DATA_DIR': self.temp.name, 'ADMIN_PASSWORD': 'test-only', 'RESEND_API_KEY': '', 'RESEND_FROM': ''})
        self.env.start()
        self.old_key = storage.register('Ana', 'ana@example.com', 'La Luna', ('pruebas.txt', b'Evidencia'), now=NOW)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_manual_request_is_safe_and_code_is_one_use(self):
        self.assertFalse(recovery.request_recovery('ana@example.com'))
        self.assertIsNotNone(storage.lookup('ana@example.com', self.old_key))
        self.assertEqual(len(recovery.pending_requests()), 1)
        code = recovery.organizer_code('ana@example.com')
        self.assertRegex(code, r'^\d{8}$')
        key = recovery.finish('ANA@example.com', code)
        self.assertIsNone(storage.lookup('ana@example.com', self.old_key))
        self.assertIsNotNone(storage.lookup('ana@example.com', key))
        self.assertEqual(storage.evidence(1), ('pruebas.txt', b'Evidencia'))
        with self.assertRaises(ValueError):
            recovery.finish('ana@example.com', code)
        self.assertEqual(recovery.pending_requests(), [])
        with self.assertRaises(storage.AlreadySubmittedError):
            storage.update(1, key, 'Ana', 'ana@example.com', 'La Luna', ('otro.txt', b'Otro'), now=NOW)

    def test_expiry_and_five_attempt_limit(self):
        self.assertTrue(recovery.request_code('ana@example.com', recovery.code_hash('12345678'), now=NOW))
        with self.assertRaises(ValueError):
            recovery.finish('ana@example.com', '12345678', now=NOW + timedelta(minutes=15))
        for _ in range(5):
            with self.assertRaises(ValueError):
                recovery.finish('ana@example.com', '87654321', now=NOW)
        with self.assertRaises(ValueError):
            recovery.finish('ana@example.com', '12345678', now=NOW)
        self.assertIsNotNone(storage.lookup('ana@example.com', self.old_key))

    def test_request_cannot_invalidate_an_active_code(self):
        recovery.request_code('ana@example.com', recovery.code_hash('12345678'), now=NOW)
        self.assertFalse(recovery.request_code('ana@example.com', None, now=NOW + timedelta(minutes=2)))
        key = recovery.finish('ana@example.com', '12345678', now=NOW + timedelta(minutes=3))
        self.assertIsNotNone(storage.lookup('ana@example.com', key))

    def test_unknown_email_sends_nothing_and_does_not_create_a_guest(self):
        with patch('recovery.resend_ready', return_value=True), patch('recovery.send_code') as send:
            recovery.request_recovery('unknown@example.com')
        send.assert_not_called()
        self.assertEqual(len(storage.guests()), 1)

    def test_resend_message_stays_on_server_and_only_sends_to_registered_email(self):
        with patch('recovery.resend_ready', return_value=True), patch('recovery.new_code', return_value='12345678'), patch('recovery.send_code') as send:
            recovery.request_recovery('ana@example.com')
            recovery.request_recovery('ana@example.com')
        send.assert_called_once_with('ana@example.com', '12345678')
        self.assertIsNotNone(storage.lookup('ana@example.com', self.old_key))

    def test_forgot_key_ui_and_generic_document_label(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
        next(c for c in app.checkbox if c.label == 'Quiero presentar').check().run()
        self.assertFalse(app.exception)
        labels = [u.proto.label for u in app.get('file_uploader')]
        self.assertEqual(labels, ['Tu documento'])
        self.assertFalse(any('PDF, KEY' in u.proto.label for u in app.get('file_uploader')))
        self.assertTrue(any('5:00 p.m.' in c.value for c in app.caption))
        self.assertFalse(any('Ciudad de México' in c.value for c in app.caption))
        app.session_state['navigation'] = '02 / Mi expediente'
        app.run()
        self.assertTrue(any('Olvidé mi clave' == e.label for e in app.expander))

    def test_deadline_accepts_afternoon_until_five(self):
        self.assertEqual(storage.DEADLINE.hour, 17)
        storage.validate_evidence('prueba.txt', b'Contenido', now=storage.DEADLINE.replace(hour=16, minute=59))
        with self.assertRaises(ValueError):
            storage.validate_evidence('prueba.txt', b'Contenido', now=storage.DEADLINE)


if __name__ == '__main__':
    unittest.main()
