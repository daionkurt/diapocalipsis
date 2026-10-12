from hashlib import sha256
from io import BytesIO
import json
import os
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import storage
from supabase_store import RemoteError, SupabaseStore, TABLE


class SupabaseTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test-only-not-a-real-key",
            "SUPABASE_STORAGE_BUCKET": "presentaciones",
        })
        self.env.start()
        self.store = SupabaseStore()

    def tearDown(self):
        self.env.stop()

    def test_partial_config_does_not_fall_back_to_local(self):
        with patch.dict(os.environ, {"SUPABASE_SECRET_KEY": ""}):
            with self.assertRaisesRegex(storage.StorageError, "Falta SUPABASE_SECRET_KEY"):
                storage.guests()

    def test_transport_secret_headers_and_safe_error(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'[]'
        with patch('supabase_store.urlopen', return_value=response) as transport:
            self.store.request('GET', TABLE)
        request = transport.call_args.args[0]
        self.assertEqual(request.get_header('Apikey'), self.store.key)
        self.assertIsNone(request.get_header('Authorization'))
        error = HTTPError('https://example.supabase.co', 401, 'denied', {}, BytesIO(json.dumps({'message': self.store.key, 'code': '401'}).encode()))
        with patch('supabase_store.urlopen', side_effect=error):
            with self.assertRaises(RemoteError) as caught:
                self.store.request('GET', TABLE)
        self.assertNotIn(self.store.key, str(caught.exception))

    def test_token_required_before_any_upload_or_write(self):
        self.store.request = Mock(return_value=[])
        self.store.upload = Mock()
        with self.assertRaisesRegex(ValueError, "clave"):
            self.store.update(7, 'wrong', 'Ana', 'ana@example.com', 'Área 51', 'Conspiraciones', ('a.pdf', b'%PDF-1.7'))
        self.store.upload.assert_not_called()
        self.assertEqual(self.store.request.call_count, 1)

    def test_update_filters_identity_and_preserves_old_file_without_upload(self):
        self.store.request = Mock(side_effect=[[{'id': 7}], [{'id': 7}]])
        self.store.update(7, 'private-token', 'Ana', 'ana@example.com', 'Área 51', 'Conspiraciones')
        call = self.store.request.call_args
        self.assertEqual(call.args, ('PATCH', TABLE))
        self.assertEqual(call.kwargs['query']['token_hash'], 'eq.' + sha256(b'private-token').hexdigest())
        self.assertNotIn('file_path', call.kwargs['payload'])

    def test_definite_duplicate_cleans_new_upload_but_timeout_keeps_it(self):
        upload = {'file_bucket': 'presentaciones', 'file_path': 'expedientes/new.pdf'}
        self.store.request = Mock(side_effect=[RemoteError(409, '23505'), None])
        with self.assertRaises(ValueError):
            self.store.write('POST', {}, None, upload)
        self.assertEqual(self.store.request.call_args.args[0], 'DELETE')
        self.store.request = Mock(side_effect=storage.StorageError('timeout'))
        with self.assertRaises(storage.StorageError):
            self.store.write('POST', {}, None, upload)
        self.assertEqual(self.store.request.call_count, 1)

    def test_lost_registration_response_recovers_exact_token(self):
        self.store.write = Mock(side_effect=storage.StorageError('timeout'))
        self.store.lookup = Mock(return_value={'id': 7})
        with patch('supabase_store.secrets.token_urlsafe', return_value='private-recovery-token'):
            token = self.store.register('Ana', 'ana@example.com', 'Área 51', 'Conspiraciones')
        self.assertEqual(token, 'private-recovery-token')
        self.store.lookup.assert_called_once_with('ana@example.com', token)

    def test_health_check_rejects_public_bucket(self):
        self.store.request = Mock(side_effect=[[], {'public': True, 'file_size_limit': 52428800}])
        with self.assertRaisesRegex(storage.StorageError, 'privado'):
            self.store.check()


if __name__ == '__main__':
    unittest.main()
