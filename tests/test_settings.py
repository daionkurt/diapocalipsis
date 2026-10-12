import os
import unittest
from unittest.mock import patch

from settings import setting


class SettingsTest(unittest.TestCase):
    def test_cloud_secrets_do_not_depend_on_a_repo_file(self):
        with patch.dict(os.environ, {}, clear=True), patch('streamlit.runtime.exists', return_value=True), patch('streamlit.secrets', {'SUPABASE_URL': 'https://cloud.supabase.co', 'SUPABASE_SECRET_KEY': 'sb_secret_test'}):
            self.assertEqual(setting('SUPABASE_URL'), 'https://cloud.supabase.co')
            self.assertEqual(setting('SUPABASE_SECRET_KEY'), 'sb_secret_test')

    def test_explicit_environment_value_has_precedence(self):
        with patch.dict(os.environ, {'SUPABASE_URL': ''}), patch('streamlit.secrets', {'SUPABASE_URL': 'https://cloud.supabase.co'}):
            self.assertEqual(setting('SUPABASE_URL'), '')


if __name__ == '__main__':
    unittest.main()
