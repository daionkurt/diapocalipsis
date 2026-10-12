"""Shared, atomic presentation draws and a code-rendered investigation wheel."""
from contextlib import closing
import json
import math
import secrets
from html import escape
import storage

TABLE = '/rest/v1/diapocalipsis_roulette'


def eligible(rows):
    return [r for r in rows if storage.is_presenter(r) and r.get('filename')]


def _local():
    conn = storage.connect()
    conn.execute('CREATE TABLE IF NOT EXISTS roulette (id INTEGER PRIMARY KEY, drawn TEXT NOT NULL, selected INTEGER)')
    conn.execute("INSERT OR IGNORE INTO roulette VALUES(1,'[]',NULL)")
    conn.commit()
    return conn


def state():
    remote = storage.remote_store()
    if remote:
        rows = remote.request('GET', TABLE, query={'select': 'drawn,selected', 'id': 'eq.1'})
        return rows[0] if rows else {'drawn': [], 'selected': None}
    with closing(_local()) as conn:
        row = conn.execute('SELECT drawn,selected FROM roulette WHERE id=1').fetchone()
        return {'drawn': json.loads(row['drawn']), 'selected': row['selected']}


def draw():
    remote = storage.remote_store()
    if remote:
        return remote.request('POST', '/rest/v1/rpc/diapocalipsis_draw', payload={})
    with closing(_local()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT drawn FROM roulette WHERE id=1').fetchone()
        drawn = json.loads(row['drawn'])
        candidates = [r['id'] for r in conn.execute('SELECT id,is_presenter,filename FROM guests LEFT JOIN evidence ON guests.id=evidence.guest_id') if r['is_presenter'] and r['filename'] and r['id'] not in drawn]
        if not candidates:
            return None
        selected = secrets.choice(candidates)
        conn.execute('UPDATE roulette SET drawn=?,selected=? WHERE id=1', (json.dumps(drawn + [selected]), selected))
        return selected


def reset():
    remote = storage.remote_store()
    if remote:
        remote.request('POST', '/rest/v1/rpc/diapocalipsis_reset_roulette', payload={})
        return
    with closing(_local()) as conn, conn:
        conn.execute("UPDATE roulette SET drawn='[]',selected=NULL WHERE id=1")


def wheel(rows, selected=None, animate=False):
    """SVG sectors follow the live candidate count; selected sector lands at the pointer."""
    rows = rows or [{'id': None, 'name': 'Esperando evidencia'}]
    n = len(rows)
    colors = ['#742b2e', '#27362f', '#63573e', '#343032']
    pieces = []
    for i, row in enumerate(rows):
        start, end = i * 2 * math.pi / n - math.pi / 2, (i + 1) * 2 * math.pi / n - math.pi / 2
        if n == 1:
            pieces.append(f'<circle cx="200" cy="200" r="184" fill="{colors[0]}"/>')
        else:
            x1,y1 = 200 + 184*math.cos(start),200 + 184*math.sin(start)
            x2,y2 = 200 + 184*math.cos(end),200 + 184*math.sin(end)
            pieces.append(f'<path d="M200 200 L{x1} {y1} A184 184 0 {int(n == 2)} 1 {x2} {y2} Z" fill="{colors[i%4]}" stroke="#b5a47c"/>')
        mid = (start+end)/2 if n > 1 else -math.pi/2
        angle = mid*180/math.pi
        label = escape(row['name'][:25]) if n <= 12 else str(i+1)
        pieces.append(f'<text transform="translate({200+116*math.cos(mid)} {200+116*math.sin(mid)}) rotate({angle+90})" text-anchor="middle" fill="#eee2c8" font-size="{max(8, min(15, 90/n))}" font-family="Georgia,serif">{label}</text>')
    index = next((i for i,r in enumerate(rows) if r['id']==selected), None)
    rotation = -(index+.5)*360/n if index is not None and n > 1 else 0
    animation = 'animation:spin 2.8s cubic-bezier(.15,.8,.2,1) both;' if animate else ''
    return f'''<style>body{{margin:0;background:transparent;color:#e8ddc5;}}.wheel{{max-width:420px;margin:auto;position:relative;}}svg{{width:100%;overflow:visible}}.disc{{transform-origin:200px 200px;transform:rotate({rotation}deg);{animation}}}@keyframes spin{{from{{transform:rotate({rotation-1440}deg)}}to{{transform:rotate({rotation}deg)}}}}@media(prefers-reduced-motion:reduce){{.disc{{animation:none}}}}</style><div class="wheel"><svg viewBox="0 0 400 410" role="img" aria-label="Ruleta de investigaciones"><g class="disc">{''.join(pieces)}</g><circle cx="200" cy="200" r="35" fill="#0d100f" stroke="#c7b488" stroke-width="2"/><text x="200" y="210" text-anchor="middle" fill="#e8ddc5" font-size="30">👁</text><path d="M183 0 L217 0 L200 33 Z" fill="#e8ddc5" stroke="#0d100f"/></svg></div>'''
