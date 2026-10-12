"""Read-only connectivity check; does not print secrets or guest data."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import StorageError
from supabase_store import SupabaseStore

if __name__ == "__main__":
    try:
        SupabaseStore().check()
    except StorageError as exc:
        print(f"Pendiente: {exc}")
        sys.exit(1)
    print("Supabase conectado: tabla disponible, bucket privado de 50 MB y todos los formatos permitidos.")
