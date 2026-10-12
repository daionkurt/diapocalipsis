import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import storage
from streamlit.testing.v1 import AppTest

BEFORE = storage.DEADLINE.replace(day=22)


class PartyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DIAPOCALIPSIS_DATA_DIR": self.temp.name, "ADMIN_PASSWORD": "test-organizer-password", "SUPABASE_URL": "", "SUPABASE_SECRET_KEY": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_private_access_duplicate_and_update(self):
        token = storage.register("Ana", "ANA@example.com", "La Luna")
        self.assertIsNone(storage.lookup("ana@example.com", "wrong"))
        self.assertIsNotNone(storage.lookup("ana@example.com", token))
        with self.assertRaises(ValueError):
            storage.register("Otra", "ana@example.com", "Otro tema")
        with self.assertRaises(ValueError):
            storage.update(1, "wrong", "Ana", "ana@example.com", "Otro tema")
        storage.update(1, token, "Ana", "ana@example.com", "Área 51", ("../pruebas.pdf", b"%PDF-1.7\ntest"), now=BEFORE)
        self.assertEqual(storage.evidence(1)[0], "pruebas.pdf")
        self.assertEqual(storage.guests()[0]["topic"], "Área 51")

    def test_upload_validation_and_deadline_are_atomic(self):
        for filename, contents, now in [("bad.pdf", b"not pdf", BEFORE), ("file.exe", b"123", BEFORE), ("valid.pdf", b"%PDF-1.7", storage.DEADLINE)]:
            with self.assertRaises(ValueError):
                storage.register("Ana", "ana@example.com", "La Luna", (filename, contents), now=now)
        self.assertEqual(storage.guests(), [])
        token = storage.register("Ana", "ana@example.com", "La Luna", ("ok.pdf", b"%PDF-1.7\noriginal"), now=BEFORE)
        with self.assertRaises(ValueError):
            storage.update(1, token, "Ana", "ana@example.com", "Changed", ("bad.pdf", b"bad"), now=BEFORE)
        self.assertEqual(storage.guests()[0]["topic"], "La Luna")
        self.assertEqual(storage.evidence(1)[1], b"%PDF-1.7\noriginal")

    def test_keynote_and_order(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("Index/Document.iwa", b"test")
        storage.register("Ana", "ana@example.com", "La Luna", ("evidence.key", buf.getvalue()), now=BEFORE)
        storage.register("Luis", "luis@example.com", "Los ovnis")
        storage.organize(1, 3, True)
        self.assertEqual([r["id"] for r in storage.guests()], [2, 1])
        self.assertTrue(storage.guests()[1]["presented"])

    def test_new_document_formats_and_invalid_content(self):
        def office_file(member):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr(member, "<document/>")
            return buf.getvalue()

        pptx = office_file("ppt/presentation.xml")
        docx = office_file("word/document.xml")
        uploads = [
            ("teoria.PPTX", pptx),
            ("notas.docx", docx),
            ("archivo.doc", bytes.fromhex("d0cf11e0a1b11ae1") + b"test"),
            ("texto.txt", "Una teoría con acentos: aparición".encode()),
            ("texto-utf16.txt", "Más evidencia".encode("utf-16")),
        ]
        for index, upload in enumerate(uploads):
            with self.subTest(filename=upload[0]):
                storage.register("Ana", f"ana{index}@example.com", "La Luna", upload, now=BEFORE)
                self.assertEqual(storage.evidence(index + 1), upload)
        for upload in [("falso.pptx", docx), ("falso.docx", pptx), ("falso.doc", b"not word"), ("falso.txt", b"binary\x00data"), ("falso.xlsx", pptx)]:
            with self.subTest(filename=upload[0]), self.assertRaises(ValueError):
                storage.validate_evidence(*upload, now=BEFORE)

    def test_registration_ui_and_admin_privacy(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.selectbox), 0)
        app.text_input[0].set_value("Ana")
        app.text_input[1].set_value("ana@example.com")
        app.text_input[2].set_value("Los secretos de la Luna")
        app.checkbox[0].check()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(storage.guests()), 1)
        self.assertTrue(app.session_state["receipt"])
        self.assertFalse(any("ana@example.com" in m.value for m in app.markdown))
        login = next(t for t in app.text_input if t.label == "Clave del organizador")
        login.set_value("test-organizer-password")
        next(b for b in app.button if b.label == "Entrar al archivo").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("ana@example.com" in m.value for m in app.markdown))


if __name__ == "__main__":
    unittest.main()
