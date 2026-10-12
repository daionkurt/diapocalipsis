"""One-use recovery codes, delivered by Resend or by the organizer in private."""
from contextlib import closing
from datetime import datetime, timedelta
from hashlib import sha256
import json
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from settings import setting
import storage

TTL = timedelta(minutes=15)
INVALID_CODE = 'El código es incorrecto, venció o ya fue usado. Solicita uno nuevo.'


def code_hash(code):
    return sha256(code.strip().encode()).hexdigest()


def new_code():
    return f'{secrets.randbelow(100000000):08d}'


def _local():
    conn = storage.connect()
    conn.execute('''CREATE TABLE IF NOT EXISTS recovery_requests (
        guest_id INTEGER PRIMARY KEY REFERENCES guests(id), requested_at TEXT NOT NULL,
        code_hash TEXT, expires_at TEXT, attempts INTEGER NOT NULL DEFAULT 0, consumed_at TEXT
    )''')
    conn.commit()
    return conn


def request_code(email, digest=None, now=None):
    email = storage.normalize_email(email)
    remote = storage.remote_store()
    if remote:
        return remote.request('POST', '/rest/v1/rpc/diapocalipsis_request_recovery', payload={'p_email': email, 'p_code_hash': digest})
    now = now or datetime.now(storage.TZ)
    with closing(_local()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        guest = conn.execute('SELECT id FROM guests WHERE email=?', (email,)).fetchone()
        if not guest:
            return False
        old = conn.execute('SELECT * FROM recovery_requests WHERE guest_id=?', (guest[0],)).fetchone()
        if old and not old['consumed_at']:
            if old['expires_at'] and datetime.fromisoformat(old['expires_at']) > now:
                return False
            if datetime.fromisoformat(old['requested_at']) + timedelta(seconds=60) > now:
                return False
        conn.execute('''INSERT OR REPLACE INTO recovery_requests VALUES(?,?,?,?,0,NULL)''',
                     (guest[0], now.isoformat(), digest, (now + TTL).isoformat() if digest else None))
        return True


def issue_code(email, digest, now=None):
    email = storage.normalize_email(email)
    remote = storage.remote_store()
    if remote:
        return remote.request('POST', '/rest/v1/rpc/diapocalipsis_issue_recovery', payload={'p_email': email, 'p_code_hash': digest})
    now = now or datetime.now(storage.TZ)
    with closing(_local()) as conn, conn:
        cur = conn.execute('''UPDATE recovery_requests SET code_hash=?, expires_at=?, attempts=0, consumed_at=NULL
            WHERE guest_id=(SELECT id FROM guests WHERE email=?)''', (digest, (now + TTL).isoformat(), email))
        return cur.rowcount == 1


def pending_requests():
    remote = storage.remote_store()
    if remote:
        return remote.request('GET', '/rest/v1/diapocalipsis_recovery_pending', query={'select': '*', 'order': 'requested_at.desc', 'limit': 50})
    with closing(_local()) as conn:
        return [dict(r) for r in conn.execute('''SELECT g.id AS guest_id,g.name,g.email,r.requested_at,r.expires_at
            FROM recovery_requests r JOIN guests g ON g.id=r.guest_id WHERE r.consumed_at IS NULL ORDER BY r.requested_at DESC LIMIT 50''')]


def finish(email, code, now=None):
    email = storage.normalize_email(email)
    token = storage.make_access_key()
    remote = storage.remote_store()
    if remote:
        try:
            ok = remote.request('POST', '/rest/v1/rpc/diapocalipsis_finish_recovery', payload={
                'p_email': email, 'p_code_hash': code_hash(code), 'p_token_hash': storage.key_hash(token)})
        except storage.StorageError:
            try:
                if storage.lookup(email, token):
                    return token
            except storage.StorageError:
                pass
            raise storage.StorageError('No pudimos confirmar la recuperación. Conserva esta clave provisional y comprueba tu expediente antes de reintentar: ' + token) from None
    else:
        now = now or datetime.now(storage.TZ)
        with closing(_local()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('''SELECT r.* FROM recovery_requests r JOIN guests g ON g.id=r.guest_id WHERE g.email=?''', (email,)).fetchone()
            ok = bool(row and row['code_hash'] and row['expires_at'] and not row['consumed_at'] and row['attempts'] < 5 and datetime.fromisoformat(row['expires_at']) > now)
            if ok and not secrets.compare_digest(row['code_hash'], code_hash(code)):
                conn.execute('UPDATE recovery_requests SET attempts=attempts+1 WHERE guest_id=?', (row['guest_id'],))
                ok = False
            elif ok:
                conn.execute('UPDATE guests SET token_hash=? WHERE id=?', (storage.key_hash(token), row['guest_id']))
                conn.execute('UPDATE recovery_requests SET consumed_at=?,code_hash=NULL WHERE guest_id=?', (now.isoformat(), row['guest_id']))
    if not ok:
        raise ValueError(INVALID_CODE)
    return token


def resend_ready():
    return bool(setting('RESEND_API_KEY') and setting('RESEND_FROM'))


def send_code(email, code):
    payload = {'from': setting('RESEND_FROM'), 'to': [email], 'subject': 'Diapocalipsis · Recupera tu expediente',
               'text': f'Tu código de recuperación es: {code}\n\nVence en 15 minutos y se puede usar una sola vez. Escríbelo en Mi expediente → Olvidé mi clave. Si no lo solicitaste, ignora este mensaje. Tu clave actual sigue activa hasta que completes la recuperación.'}
    request = Request('https://api.resend.com/emails', data=json.dumps(payload).encode(), method='POST', headers={
        'Authorization': 'Bearer ' + setting('RESEND_API_KEY'), 'Content-Type': 'application/json', 'User-Agent': 'Diapocalipsis/1.0'})
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
            if not result.get('id'):
                raise storage.StorageError('No pudimos confirmar el envío del código. Contacta al organizador.')
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise storage.StorageError('No pudimos confirmar el envío del código. Contacta al organizador.') from None


def request_recovery(email):
    email = storage.normalize_email(email)
    automatic = resend_ready()
    code = new_code() if automatic else None
    if request_code(email, code_hash(code) if code else None) and automatic:
        send_code(email, code)
    return automatic


def organizer_code(email):
    code = new_code()
    if not issue_code(email, code_hash(code)):
        raise ValueError('No existe una solicitud de recuperación para este correo.')
    return code
