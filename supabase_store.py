"""Supabase REST/Storage backend. Credentials and files stay on the server."""
from hashlib import sha256
import json
from pathlib import Path
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from settings import setting
from storage import StorageError, content_type, CONTENT_TYPES

TABLE = "/rest/v1/diapocalipsis_guests"
LIST_COLUMNS = "id,name,email,topic,created_at,position,presented,filename"


class RemoteError(StorageError):
    def __init__(self, status, code):
        self.status = status
        self.code = code
        super().__init__("Supabase no pudo completar la operación. Revisa conexión, tablas y configuración.")


class SupabaseStore:
    def __init__(self):
        self.url = setting("SUPABASE_URL").rstrip("/")
        self.key = setting("SUPABASE_SECRET_KEY")
        self.bucket = setting("SUPABASE_STORAGE_BUCKET", "presentaciones")
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise StorageError("Configura una SUPABASE_URL válida: https://TU-PROYECTO.supabase.co")
        if not self.key or self.key.startswith("sb_publishable_"):
            raise StorageError("Falta SUPABASE_SECRET_KEY en .streamlit/secrets.toml. Usa una clave secreta de servidor.")
        if not self.bucket:
            raise StorageError("Configura SUPABASE_STORAGE_BUCKET con el nombre de tu bucket privado.")

    def request(self, method, path, *, query=None, payload=None, contents=None, content_type=None, raw=False):
        headers = {"apikey": self.key, "Accept": "application/json", "Prefer": "return=representation"}
        # Secret keys are not JWTs: authenticate with apikey, never use them as Bearer tokens.
        if self.key.startswith("eyJ"):
            headers["Authorization"] = "Bearer " + self.key
        if payload is not None:
            contents = json.dumps(payload).encode()
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        url = self.url + path
        if query:
            url += "?" + urlencode(query)
        request = Request(url, data=contents, headers=headers, method=method)
        try:
            with urlopen(request, timeout=120 if contents and len(contents) > 1024 * 1024 else 30) as response:
                body = response.read()
                return body if raw else json.loads(body) if body else None
        except HTTPError as exc:
            try:
                code = str(json.loads(exc.read()).get("code", ""))
            except (ValueError, AttributeError):
                code = ""
            # Never expose response bodies, request headers or credentials to the UI.
            raise RemoteError(exc.code, code) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise StorageError("No pudimos confirmar la respuesta de Supabase. Revisa la conexión antes de reintentar.") from None

    def object_route(self, bucket, path):
        return "/storage/v1/object/" + quote(bucket, safe="") + "/" + quote(path, safe="/")

    def upload(self, filename, contents):
        path = f"expedientes/{uuid4().hex}{Path(filename).suffix.lower()}"
        mime = content_type(filename)
        self.request("POST", self.object_route(self.bucket, path), contents=contents, content_type=mime)
        return {"filename": filename, "file_path": path, "file_bucket": self.bucket}

    def discard_rejected_upload(self, uploaded):
        """Only discard new objects after a definitive SQL rejection, never after timeouts."""
        if uploaded:
            try:
                self.request("DELETE", "/storage/v1/object/" + quote(uploaded["file_bucket"], safe=""), payload={"prefixes": [uploaded["file_path"]]})
            except StorageError:
                pass  # An unlinked private object is safe to retain for manual cleanup.

    def write(self, method, payload, query, uploaded):
        try:
            return self.request(method, TABLE, payload=payload, query=query)
        except RemoteError as exc:
            if exc.code in {"23505", "23514", "P0001"}:
                self.discard_rejected_upload(uploaded)
            if exc.code == "23505":
                raise ValueError("Este correo ya tiene un expediente. Usa su clave privada para actualizarlo.") from None
            if exc.code == "P0001":
                raise ValueError("No se aceptó el archivo: la recepción cerró o la evidencia no está disponible en el bucket privado.") from None
            raise

    def register(self, name, email, topic, upload=None):
        token = secrets.token_urlsafe(32)
        uploaded = self.upload(*upload) if upload else None
        payload = {"name": name, "email": email, "topic": topic, "category": "Otro misterio", "token_hash": sha256(token.encode()).hexdigest()}
        if uploaded:
            payload.update(uploaded)
        try:
            self.write("POST", payload, None, uploaded)
        except StorageError:
            # The server may have committed despite a lost response. Recover this exact registration.
            try:
                if self.lookup(email, token):
                    return token
            except StorageError:
                pass
            raise StorageError("No pudimos confirmar el registro. Guarda esta clave temporal y consulta Mi expediente antes de reintentar: " + token) from None
        return token

    def lookup(self, email, token):
        rows = self.request("GET", TABLE, query={"select": "*", "email": "eq." + email.strip().lower(), "limit": 1})
        if rows and secrets.compare_digest(rows[0]["token_hash"], sha256(token.strip().encode()).hexdigest()):
            return rows[0]
        return None

    def update(self, guest_id, token, name, email, topic, upload=None):
        token_hash = sha256(token.strip().encode()).hexdigest()
        matches = self.request("GET", TABLE, query={"select": "id", "id": f"eq.{guest_id}", "token_hash": "eq." + token_hash, "limit": 1})
        if not matches:
            raise ValueError("La clave de acceso no coincide.")
        uploaded = self.upload(*upload) if upload else None
        payload = {"name": name, "email": email, "topic": topic}
        if uploaded:
            payload.update(uploaded)
        rows = self.write("PATCH", payload, {"id": f"eq.{guest_id}", "token_hash": "eq." + token_hash}, uploaded)
        if not rows:
            self.discard_rejected_upload(uploaded)
            raise ValueError("No se encontró el expediente autorizado.")
        # Replaced files retain private versions; uncertain/concurrent writes cannot destroy evidence.

    def guests(self):
        rows = []
        offset = 0
        while True:
            page = self.request("GET", TABLE, query={"select": LIST_COLUMNS, "order": "id.asc", "offset": offset, "limit": 500})
            rows.extend(page)
            if len(page) < 500:
                break
            offset += len(page)
        for row in rows:
            row["position"] = row["position"] or row["id"]
        return sorted(rows, key=lambda r: (r["position"], r["id"]))

    def evidence(self, guest_id):
        rows = self.request("GET", TABLE, query={"select": "filename,file_path,file_bucket", "id": f"eq.{guest_id}", "limit": 1})
        if not rows or not rows[0]["file_path"]:
            return None
        row = rows[0]
        contents = self.request("GET", self.object_route(row["file_bucket"], row["file_path"]), raw=True)
        return row["filename"], contents

    def evidence_name(self, guest_id):
        rows = self.request("GET", TABLE, query={"select": "filename", "id": f"eq.{guest_id}", "limit": 1})
        return rows[0]["filename"] if rows else None

    def organize(self, guest_id, position, presented):
        self.request("PATCH", TABLE, query={"id": f"eq.{guest_id}"}, payload={"position": position, "presented": bool(presented)})

    def check(self):
        self.request("GET", TABLE, query={"select": "id", "limit": 1})
        bucket = self.request("GET", "/storage/v1/bucket/" + quote(self.bucket, safe=""))
        if bucket.get("public") is not False:
            raise StorageError("El bucket de presentaciones debe ser privado.")
        if not bucket.get("file_size_limit") or bucket["file_size_limit"] < 50 * 1024 * 1024:
            raise StorageError("El bucket debe permitir archivos de hasta 50 MB.")
        allowed = bucket.get("allowed_mime_types")
        if allowed is not None and not set(CONTENT_TYPES.values()).issubset(allowed):
            raise StorageError("Faltan formatos permitidos en el bucket. Ejecuta supabase/update_formats.sql en SQL Editor.")
