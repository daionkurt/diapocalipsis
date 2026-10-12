"""Validated storage facade: local SQLite or server-side Supabase."""
from contextlib import closing
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import os
import re
import secrets
import sqlite3
import zipfile
from zoneinfo import ZoneInfo
from settings import setting

TZ = ZoneInfo("America/Mexico_City")
DEADLINE = datetime(2026, 10, 23, 17, tzinfo=TZ)
EVENT = datetime(2026, 10, 23, 18, 30, tzinfo=TZ)
MAX_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = ["pdf", "key", "pptx", "doc", "docx", "txt"]
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".key": "application/octet-stream",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}
KEY_WORDS = (
    "luna", "ovni", "nave", "bruja", "sombra", "cuervo", "bosque", "noche",
    "niebla", "brujo", "rayo", "astro", "portal", "cosmos", "cometa", "saturno",
    "marte", "venus", "orion", "pluton", "dragon", "kraken", "momia", "duende",
    "troll", "hada", "elfo", "ogro", "lobo", "gato", "buho", "runa",
    "capa", "cetro", "vela", "craneo", "torre", "cripta", "tumba", "castillo",
    "eco", "susurro", "enigma", "arcano", "hechizo", "ritual", "amuleto", "aura",
    "alien", "mutante", "espectro", "fantasma", "zombi", "vampiro", "sable", "reliquia",
    "eclipse", "estrella", "galaxia", "abismo", "destino", "secreto", "mito", "magia",
)


def make_access_key():
    return f"{secrets.choice(KEY_WORDS)}-{secrets.choice(KEY_WORDS)}-{secrets.randbelow(10000):04d}"


def key_hash(token):
    token = token.strip()
    # New memorable keys ignore letter case; existing long keys keep their original spelling.
    if re.fullmatch(r"[A-Za-z]+-[A-Za-z]+-\d{4}", token):
        token = token.lower()
    return sha256(token.encode()).hexdigest()


def content_type(filename):
    return CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


class StorageError(Exception):
    """Safe, actionable storage error that can be shown to a guest."""


class AlreadySubmittedError(ValueError):
    def __init__(self):
        super().__init__("Este correo ya subió un documento. Tu evidencia ya está recibida; no puedes subir otra.")


class AlreadyRegisteredError(ValueError):
    def __init__(self):
        super().__init__("Este correo ya está registrado. Abre Mi expediente con tu clave para completar tu entrega.")


def remote_store():
    backend = setting("STORAGE_BACKEND", "supabase")
    if backend == "sqlite":
        return None
    if backend != "supabase":
        raise StorageError("STORAGE_BACKEND debe ser supabase o sqlite.")
    from supabase_store import SupabaseStore
    return SupabaseStore()


def db_path():
    return Path(os.environ.get("DIAPOCALIPSIS_DATA_DIR", Path(__file__).parent / "data")) / "expedientes.sqlite3"


def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS guests (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
        topic TEXT NOT NULL, category TEXT NOT NULL, token_hash TEXT NOT NULL,
        created_at TEXT NOT NULL, position INTEGER NOT NULL,
        presented INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS evidence (
        guest_id INTEGER PRIMARY KEY REFERENCES guests(id),
        filename TEXT NOT NULL, contents BLOB NOT NULL, updated_at TEXT NOT NULL
    );
    """)
    if 'is_presenter' not in {r[1] for r in conn.execute('PRAGMA table_info(guests)')}:
        conn.execute('ALTER TABLE guests ADD COLUMN is_presenter INTEGER NOT NULL DEFAULT 1')
        conn.commit()
    return conn


def is_presenter(guest):
    return bool(guest.get('is_presenter', True))


def normalize_email(email):
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Escribe un correo válido para tu expediente.")
    return email


def validate_fields(name, email, topic):
    name, email, topic = name.strip(), normalize_email(email), topic.strip()
    if not 2 <= len(name) <= 80:
        raise ValueError("Escribe tu nombre (entre 2 y 80 caracteres).")
    if not 3 <= len(topic) <= 160:
        raise ValueError("Escribe tu tema (entre 3 y 160 caracteres).")
    return name, email, topic


def validate_evidence(filename, contents, now=None):
    if (now or datetime.now(TZ)) >= DEADLINE:
        raise ValueError("La recepción de evidencia cerró el 23 de octubre a las 5:00 p.m.")
    if not contents or len(contents) > MAX_BYTES:
        raise ValueError("El archivo debe pesar entre 1 byte y 50 MB.")
    filename = Path(filename.replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        if not contents.startswith(b"%PDF-"):
            raise ValueError("Ese archivo no tiene una cabecera PDF válida.")
    elif suffix in {".key", ".pptx", ".docx"}:
        try:
            with zipfile.ZipFile(BytesIO(contents)) as archive:
                names = archive.namelist()
                if suffix == ".pptx" and not {"[Content_Types].xml", "ppt/presentation.xml"}.issubset(names):
                    raise ValueError("El archivo no parece una presentación PPTX válida.")
                if suffix == ".docx" and not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                    raise ValueError("El archivo no parece un documento Word DOCX válido.")
                if suffix == ".key" and not any(n.startswith("Index/") or n.endswith("index.apxl") for n in names):
                    raise ValueError("El archivo no parece una presentación de Keynote. Exporta a PDF si es necesario.")
        except zipfile.BadZipFile:
            raise ValueError("No se reconoce el documento. Usa un archivo KEY, PPTX o DOCX válido, o exporta a PDF.") from None
    elif suffix == ".doc":
        if not contents.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise ValueError("El archivo no tiene una cabecera Word DOC válida. Guarda como DOCX o PDF.")
    elif suffix == ".txt":
        encoding = "utf-16" if contents.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        try:
            text = contents.decode(encoding)
        except UnicodeDecodeError:
            try:
                text = contents.decode("cp1252")
            except UnicodeDecodeError:
                raise ValueError("No se reconoce el texto. Guarda tu TXT con codificación UTF-8.") from None
        if any((ord(c) < 32 and c not in "\n\r\t\f") or ord(c) == 127 for c in text):
            raise ValueError("El TXT contiene datos binarios. Sube un archivo de texto legible.")
    else:
        raise ValueError("Recibimos PDF, KEY, PPTX, Word (.doc/.docx) o TXT.")
    return filename


def register(name, email, topic="", upload=None, now=None, presenting=True):
    if not presenting:
        if upload:
            raise ValueError("Solo quienes presentan pueden entregar un documento.")
        topic = "Solo asistencia"
    name, email, topic = validate_fields(name, email, topic)
    filename = validate_evidence(*upload, now=now) if upload else None
    remote = remote_store()
    if remote:
        return remote.register(name, email, topic, (filename, upload[1]) if upload else None, presenting=presenting)
    token = make_access_key()
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT e.guest_id FROM guests g LEFT JOIN evidence e ON e.guest_id=g.id WHERE g.email=?", (email,)).fetchone()
        if existing and existing[0] is not None:
            raise AlreadySubmittedError()
        if existing:
            raise AlreadyRegisteredError()
        position = conn.execute("SELECT COALESCE(MAX(position), 0)+1 FROM guests").fetchone()[0]
        try:
            cur = conn.execute(
                "INSERT INTO guests(name,email,topic,category,token_hash,created_at,position,is_presenter) VALUES(?,?,?,?,?,?,?,?)",
                (name, email, topic, "Otro misterio", key_hash(token), datetime.now(TZ).isoformat(), position, int(presenting)),
            )
        except sqlite3.IntegrityError:
            raise AlreadyRegisteredError() from None
        if upload:
            conn.execute("INSERT INTO evidence VALUES(?,?,?,?)", (cur.lastrowid, filename, upload[1], datetime.now(TZ).isoformat()))
    return token


def lookup(email, token):
    remote = remote_store()
    if remote:
        return remote.lookup(email, token)
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM guests WHERE email=?", (email.strip().lower(),)).fetchone()
    if row and secrets.compare_digest(row["token_hash"], key_hash(token)):
        return dict(row)
    return None


def update(guest_id, token, name, email, topic, upload=None, now=None, presenting=None):
    if presenting is False:
        if upload:
            raise ValueError("Activa Quiero presentar para entregar un documento.")
        topic = "Solo asistencia"
    name, email, topic = validate_fields(name, email, topic)
    filename = validate_evidence(*upload, now=now) if upload else None
    remote = remote_store()
    if remote:
        return remote.update(guest_id, token, name, email, topic, (filename, upload[1]) if upload else None, presenting=presenting)
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT token_hash FROM guests WHERE id=?", (guest_id,)).fetchone()
        if not row or not secrets.compare_digest(row[0], key_hash(token)):
            raise ValueError("La clave de acceso no coincide.")
        if conn.execute("SELECT 1 FROM evidence WHERE guest_id=?", (guest_id,)).fetchone():
            raise AlreadySubmittedError()
        try:
            conn.execute("UPDATE guests SET name=?,email=?,topic=?,is_presenter=COALESCE(?,is_presenter) WHERE id=?", (name, email, topic, presenting, guest_id))
        except sqlite3.IntegrityError:
            raise ValueError("Ese correo ya pertenece a otro expediente.") from None
        if upload:
            conn.execute("INSERT INTO evidence VALUES(?,?,?,?)", (guest_id, filename, upload[1], datetime.now(TZ).isoformat()))


def remove_evidence(guest_id, token):
    """Remove only the authenticated guest's current evidence, retaining registration."""
    remote = remote_store()
    if remote:
        return remote.remove_evidence(guest_id, token)
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        guest = conn.execute("SELECT token_hash FROM guests WHERE id=?", (guest_id,)).fetchone()
        if not guest or not secrets.compare_digest(guest[0], key_hash(token)):
            raise ValueError("La clave de acceso no coincide.")
        conn.execute("DELETE FROM evidence WHERE guest_id=?", (guest_id,))
    return True


def set_presenting(guest_id, token, presenting):
    """Change participation without replacing submitted evidence or contact details."""
    remote = remote_store()
    if remote:
        return remote.set_presenting(guest_id, token, presenting)
    with closing(connect()) as conn, conn:
        cur = conn.execute("UPDATE guests SET is_presenter=? WHERE id=? AND token_hash=?",
                           (int(presenting), guest_id, key_hash(token)))
        if cur.rowcount != 1:
            raise ValueError("La clave de acceso no coincide.")


def guests():
    remote = remote_store()
    if remote:
        return remote.guests()
    with closing(connect()) as conn:
        return [dict(r) for r in conn.execute("""SELECT g.id,g.name,g.email,g.topic,g.is_presenter,g.created_at,g.position,g.presented,
            e.filename FROM guests g LEFT JOIN evidence e ON e.guest_id=g.id ORDER BY g.position,g.id""")]


def evidence(guest_id):
    remote = remote_store()
    if remote:
        return remote.evidence(guest_id)
    with closing(connect()) as conn:
        row = conn.execute("SELECT filename,contents FROM evidence WHERE guest_id=?", (guest_id,)).fetchone()
        return tuple(row) if row else None


def organize(guest_id, position, presented):
    remote = remote_store()
    if remote:
        return remote.organize(guest_id, position, presented)
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE guests SET position=?,presented=? WHERE id=?", (position, int(presented), guest_id))


def evidence_name(guest_id):
    remote = remote_store()
    if remote:
        return remote.evidence_name(guest_id)
    with closing(connect()) as conn:
        row = conn.execute("SELECT filename FROM evidence WHERE guest_id=?", (guest_id,)).fetchone()
        return row[0] if row else None


def registration_status(email):
    """Return only enrollment/upload flags; email alone never grants private access."""
    email = email.strip().lower()
    remote = remote_store()
    if remote:
        return remote.registration_status(email)
    with closing(connect()) as conn:
        row = conn.execute("SELECT e.guest_id FROM guests g LEFT JOIN evidence e ON e.guest_id=g.id WHERE g.email=?", (email,)).fetchone()
        return {"registered": row is not None, "submitted": bool(row and row[0] is not None)}
