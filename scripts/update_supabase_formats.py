"""Add the app's document MIME types to the existing private bucket."""
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import CONTENT_TYPES, StorageError
from supabase_store import SupabaseStore


def update_formats():
    store = SupabaseStore()
    route = '/storage/v1/bucket/' + quote(store.bucket, safe='')
    bucket = store.request('GET', route)
    if bucket.get('public') is not False:
        raise StorageError('El bucket debe ser privado antes de actualizar sus formatos.')
    allowed = bucket.get('allowed_mime_types')
    if allowed is not None:
        supported = sorted(set(allowed) | set(CONTENT_TYPES.values()))
        store.request('PUT', route, payload={'allowedMimeTypes': supported})
    store.check()
    print('Bucket verificado: privado, 50 MB, PDF, KEY, PPTX, DOC, DOCX y TXT permitidos.')


if __name__ == '__main__':
    try:
        update_formats()
    except StorageError as exc:
        print(f'Pendiente: {exc}')
        sys.exit(1)
