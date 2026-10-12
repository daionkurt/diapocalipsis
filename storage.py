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
DEADLINE = datetime(2026, 10, 23, 12, tzinfo=TZ)
EVENT = datetime(2026, 10, 23, 18, 30, tzinfo=TZ)
MAX_BYTES = 50 * 1024 * 1024


class StorageError(Exception):
    """Safe, actionable storage error that can be shown to a guest."""


def remote_store():
    if setting("SUPABASE_URL") or setting("SUPABASE_SECRET_KEY"):
        from supabase_store import SupabaseStore
        return SupabaseStore()
    return None


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
    return conn


def validate_fields(name, email, topic):
    name, email, topic = name.strip(), email.strip().lower(), topic.strip()
    if not 2 <= len(name) <= 80:
        raise ValueError("Escribe tu nombre (entre 2 y 80 caracteres).")
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Escribe un correo válido para tu expediente.")
    if not 3 <= len(topic) <= 160:
        raise ValueError("Escribe tu tema (entre 3 y 160 caracteres).")
    return name, email, topic


def validate_evidence(filename, contents, now=None):
    if (now or datetime.now(TZ)) >= DEADLINE:
        raise ValueError("La recepción de evidencia cerró el 23 de octubre a las 12:00 p.m.")
    if not contents or len(contents) > MAX_BYTES:
        raise ValueError("El archivo debe pesar entre 1 byte y 50 MB.")
    filename = Path(filename.replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        if not contents.startswith(b"%PDF-"):
            raise ValueError("Ese archivo no tiene una cabecera PDF válida.")
    elif suffix == ".key":
        try:
            with zipfile.ZipFile(BytesIO(contents)) as archive:
                names = archive.namelist()
                if not any(n.startswith("Index/") or n.endswith("index.apxl") for n in names):
                    raise ValueError("El archivo no parece una presentación de Keynote. Exporta a PDF si es necesario.")
        except zipfile.BadZipFile:
            raise ValueError("No se reconoce este Keynote. Guarda como archivo .key o exporta a PDF.") from None
    else:
        raise ValueError("Solo recibimos PDF (.pdf) o Keynote (.key).")
    return filename


def register(name, email, topic, category, upload=None, now=None):
    name, email, topic = validate_fields(name, email, topic)
    filename = validate_evidence(*upload, now=now) if upload else None
    remote = remote_store()
    if remote:
        return remote.register(name, email, topic, category, (filename, upload[1]) if upload else None)
    token = secrets.token_urlsafe(32)
    with closing(connect()) as conn, conn:
        position = conn.execute("SELECT COALESCE(MAX(position), 0)+1 FROM guests").fetchone()[0]
        try:
            cur = conn.execute(
                "INSERT INTO guests(name,email,topic,category,token_hash,created_at,position) VALUES(?,?,?,?,?,?,?)",
                (name, email, topic, category, sha256(token.encode()).hexdigest(), datetime.now(TZ).isoformat(), position),
            )
        except sqlite3.IntegrityError:
            raise ValueError("Este correo ya tiene un expediente. Usa tu clave en ‘Mi expediente’ para actualizarlo.") from None
        if upload:
            conn.execute("INSERT INTO evidence VALUES(?,?,?,?)", (cur.lastrowid, filename, upload[1], datetime.now(TZ).isoformat()))
    return token


def lookup(email, token):
    remote = remote_store()
    if remote:
        return remote.lookup(email, token)
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM guests WHERE email=?", (email.strip().lower(),)).fetchone()
    if row and secrets.compare_digest(row["token_hash"], sha256(token.strip().encode()).hexdigest()):
        return dict(row)
    return None


def update(guest_id, token, name, email, topic, category, upload=None, now=None):
    name, email, topic = validate_fields(name, email, topic)
    filename = validate_evidence(*upload, now=now) if upload else None
    remote = remote_store()
    if remote:
        return remote.update(guest_id, token, name, email, topic, category, (filename, upload[1]) if upload else None)
    with closing(connect()) as conn, conn:
        row = conn.execute("SELECT token_hash FROM guests WHERE id=?", (guest_id,)).fetchone()
        if not row or not secrets.compare_digest(row[0], sha256(token.strip().encode()).hexdigest()):
            raise ValueError("La clave de acceso no coincide.")
        try:
            conn.execute("UPDATE guests SET name=?,email=?,topic=?,category=? WHERE id=?", (name, email, topic, category, guest_id))
        except sqlite3.IntegrityError:
            raise ValueError("Ese correo ya pertenece a otro expediente.") from None
        if upload:
            conn.execute("INSERT OR REPLACE INTO evidence VALUES(?,?,?,?)", (guest_id, filename, upload[1], datetime.now(TZ).isoformat()))


def guests():
    remote = remote_store()
    if remote:
        return remote.guests()
    with closing(connect()) as conn:
        return [dict(r) for r in conn.execute("""SELECT g.id,g.name,g.email,g.topic,g.category,g.created_at,g.position,g.presented,
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
