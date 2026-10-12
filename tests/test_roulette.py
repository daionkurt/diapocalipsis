import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from streamlit.testing.v1 import AppTest
import storage
import roulette


class RouletteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'STORAGE_BACKEND':'sqlite','DIAPOCALIPSIS_DATA_DIR':self.temp.name,'ADMIN_PASSWORD':'test-private-password'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_no_repeats_and_reset_with_concurrent_draws(self):
        for i in range(4):
            storage.register(f'Agente {i}',f'agent{i}@example.com','Teoría secreta',('secret.txt',b'prueba'))
        storage.register('Oyente','listener@example.com',presenting=False)
        storage.register('Pendiente','pending@example.com','La Luna')
        roulette.state()
        with ThreadPoolExecutor(max_workers=4) as pool:
            draws=list(pool.map(lambda _: roulette.draw(),range(4)))
        self.assertEqual(set(draws),{1,2,3,4})
        self.assertIsNone(roulette.draw())
        self.assertEqual(len(roulette.state()['drawn']),4)
        roulette.reset()
        self.assertEqual(roulette.state(),{'drawn':[],'selected':None})
        self.assertIn(roulette.draw(),draws)

    def test_private_admin_tab_and_no_public_file_download(self):
        storage.register('Agente','agent@example.com','La Luna',('secret.txt',b'privado'))
        roulette.draw()
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        self.assertNotIn('⌑ Organizador',[t.label for t in app.tabs])
        self.assertEqual(app.tabs[-1].label,'05 / Investigaciones')
        self.assertFalse(any(b.label=='Descargar presentación elegida' for b in app.get('download_button')))
        app.query_params['admin']='true'
        app.run()
        self.assertEqual(app.tabs[-1].label,'⌑ Organizador')
        self.assertFalse(any(b.label=='Descargar presentación elegida' for b in app.get('download_button')))
        app.session_state['admin_authenticated']=True
        app.run()
        self.assertTrue(any(b.label=='Descargar presentación elegida' for b in app.get('download_button')))

    def test_wheel_escapes_names_and_uses_selected_sector(self):
        markup=roulette.wheel([{'id':1,'name':'<script>evil</script>'},{'id':2,'name':'Ana'}],2,True)
        self.assertNotIn('<script>',markup)
        self.assertIn('rotate(-270.0deg)',markup)
        self.assertIn('animation:spin',markup)
