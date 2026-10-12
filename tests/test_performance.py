import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import storage
import roulette

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class PerformanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'STORAGE_BACKEND':'sqlite', 'DIAPOCALIPSIS_DATA_DIR':self.temp.name, 'ADMIN_PASSWORD':'test-only'})
        self.env.start()
        self.tokens = [storage.register(f'Agente {i}', f'agent{i}@example.invalid', 'La Luna', ('evidencia.txt', b'prueba')) for i in range(5)]
        roulette.draw()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_registration_does_not_run_hidden_tabs_or_fetch_files(self):
        app=AppTest.from_file(APP)
        app.query_params['admin']='true'
        app.session_state['admin_authenticated']=True
        app.session_state['guest_access']=(1,self.tokens[0],'agent0@example.invalid')
        with patch('storage.evidence', side_effect=AssertionError('unexpected file download')) as files, patch('roulette.state', side_effect=AssertionError('hidden roulette ran')) as state, patch('storage.guests', wraps=storage.guests) as rows:
            app.run()
            self.assertFalse(app.exception)
            next(c for c in app.checkbox if c.label=='Quiero presentar').check().run()
            self.assertFalse(app.exception)
            self.assertEqual(rows.call_count,1)
            self.assertEqual(files.call_count,0)
            self.assertEqual(state.call_count,0)

    def test_admin_render_defers_all_file_fetches(self):
        app=AppTest.from_file(APP)
        app.query_params['admin']='true'
        app.session_state['navigation']='⌑ Organizador'
        app.session_state['admin_authenticated']=True
        with patch('storage.evidence', side_effect=AssertionError('eager file download')) as files:
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(files.call_count,0)
            self.assertEqual(sum(i.proto.label=='Descargar evidencia' for i in app.get('download_button')),5)

    def test_draw_uses_one_mutation_and_one_state_read(self):
        app=AppTest.from_file(APP)
        app.session_state['navigation']='05 / Investigaciones'
        app.query_params['admin']='true'
        app.session_state['admin_authenticated']=True
        app.run()
        with patch('roulette.draw', wraps=roulette.draw) as draw, patch('roulette.state', wraps=roulette.state) as state, patch('storage.evidence', side_effect=AssertionError('eager file download')) as files, patch('storage.guests', wraps=storage.guests) as rows:
            next(b for b in app.button if b.label=='Iniciar investigaciones 👁').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(draw.call_count,1)
            self.assertEqual(state.call_count,1)
            self.assertEqual(rows.call_count,0)
            self.assertEqual(files.call_count,0)
