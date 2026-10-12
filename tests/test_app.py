import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import storage
from streamlit.testing.v1 import AppTest

BEFORE = storage.DEADLINE.replace(day=22)


class PartyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"STORAGE_BACKEND": "sqlite", "DIAPOCALIPSIS_DATA_DIR": self.temp.name, "ADMIN_PASSWORD": "test-organizer-password", "SUPABASE_URL": "", "SUPABASE_SECRET_KEY": ""})
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

    def test_memorable_key_case_and_old_key_compatibility(self):
        token = storage.register("Ana", "ana@example.com", "La Luna")
        self.assertRegex(token, r"^[a-z]+-[a-z]+-\d{4}$")
        self.assertIsNotNone(storage.lookup("ANA@example.com", token.upper()))
        old_token = "Old_CaseSensitive_Key_123"
        with closing(storage.connect()) as conn, conn:
            conn.execute("UPDATE guests SET token_hash=? WHERE id=1", (storage.key_hash(old_token),))
        self.assertIsNotNone(storage.lookup("ana@example.com", old_token))
        self.assertIsNone(storage.lookup("ana@example.com", old_token.lower()))

    def test_one_submission_by_email_and_no_email_change(self):
        token = storage.register("Ana", "ana@example.com", "La Luna", ("primero.txt", b"Original"), now=BEFORE)
        with self.assertRaises(storage.AlreadySubmittedError):
            storage.register("Ana", " ANA@example.com ", "La Luna", ("segundo.txt", b"Nuevo"), now=BEFORE)
        with self.assertRaises(storage.AlreadySubmittedError):
            storage.update(1, token, "Ana", "otro@example.com", "Otro tema", ("segundo.txt", b"Nuevo"), now=BEFORE)
        self.assertEqual(storage.evidence(1), ("primero.txt", b"Original"))
        self.assertEqual(storage.guests()[0]["email"], "ana@example.com")

    def test_pending_registration_cannot_be_registered_again(self):
        storage.register("Ana", "ana@example.com", "La Luna")
        with self.assertRaises(storage.AlreadyRegisteredError):
            storage.register("Otra Ana", " ANA@example.com ", "Otro tema", ("nuevo.txt", b"Nuevo"), now=BEFORE)
        self.assertEqual(len(storage.guests()), 1)
        self.assertIsNone(storage.evidence(1))

    def test_security_protocol_only_appears_for_a_pending_file(self):
        path = str(Path(__file__).resolve().parents[1] / "app.py")
        app = AppTest.from_file(path).run()
        self.assertFalse(any("Protocolo de Seguridad" in item.value for item in app.warning))
        self.assertFalse(any("Protocolo de Seguridad" in c.label for c in app.checkbox))
        app.session_state["pending_document"] = {
            "action": "register", "name": "Ana", "email": "ana@example.com", "topic": "La Luna",
            "upload": ("pruebas.txt", b"Evidencia"),
        }
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Protocolo de Seguridad" in item.value for item in app.warning))
        next(b for b in app.button if b.label == "Enviar mi documento").click().run()
        self.assertEqual(storage.guests(), [])
        next(c for c in app.checkbox if "Protocolo de Seguridad" in c.label).check()
        next(b for b in app.button if b.label == "Enviar mi documento").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(storage.evidence(1), ("pruebas.txt", b"Evidencia"))
        self.assertEqual(len(app.get("file_uploader")), 0)
        self.assertTrue(any("Ya subiste" in item.value for item in app.success))

    def test_simultaneous_submissions_only_accept_one(self):
        token = storage.register("Ana", "ana@example.com", "La Luna")
        def submit(index):
            try:
                storage.update(1, token, "Ana", "ana@example.com", "La Luna", (f"{index}.txt", str(index).encode()), now=BEFORE)
                return True
            except storage.AlreadySubmittedError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(submit, range(2))), 1)

    def test_success_hides_form_and_refresh_detects_email(self):
        token = storage.register("Ana", "ana@example.com", "La Luna", ("pruebas.txt", b"Evidencia"), now=BEFORE)
        path = str(Path(__file__).resolve().parents[1] / "app.py")
        app = AppTest.from_file(path)
        app.session_state["receipt"] = token
        app.session_state["receipt_email"] = "ana@example.com"
        app.session_state["guest_access"] = (1, token, "ana@example.com")
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("file_uploader")), 0)
        self.assertFalse(any(b.label == "Confirmar mi asistencia  →" for b in app.button))
        self.assertTrue(any("Ya subiste" in s.value for s in app.success))
        self.assertTrue(any("pruebas.txt" in m.value for m in app.markdown))
        fresh = AppTest.from_file(path).run()
        next(t for t in fresh.text_input if t.label == "Tu correo").set_value("ANA@example.com")
        next(b for b in fresh.button if b.label.startswith("Confirmar mi asistencia")).click().run()
        self.assertFalse(fresh.exception)
        self.assertEqual(len(fresh.get("file_uploader")), 0)
        self.assertTrue(any("ya subió" in s.value for s in fresh.success))

    def test_registration_ui_and_admin_privacy(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.selectbox), 0)
        next(t for t in app.text_input if t.label == "Tu nombre").set_value("Ana")
        next(t for t in app.text_input if t.label == "Tu correo").set_value("ana@example.com")
        next(t for t in app.text_input if t.label == "El tema de tu presentación").set_value("Los secretos de la Luna")
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
