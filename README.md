# Diapocalipsis 👁️

App en **Streamlit**, en español, para una noche de presentaciones sobre conspiraciones, sucesos paranormales y seres de otros mundos. Su diseño toma el negro, marfil, rojo oscuro y tipografía serif de la invitación original, incluida en `assets/invitacion.png`.

## Ejecutar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Abre http://localhost:8501. Desde otro equipo, usa la dirección de red que muestra Streamlit y permite el acceso en tu red local.

## Organizador

Esta instalación ya tiene una clave aleatoria local en `.streamlit/secrets.toml` (excluida de Git). Consulta ese archivo para entrar al panel.

En una instalación nueva, copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y reemplaza el valor de `ADMIN_PASSWORD` con tu propia contraseña larga. También puedes configurarla como variable de entorno. Sin contraseña, el panel permanece cerrado. No publiques tu archivo de secretos.

El panel permite ver correos, descargar presentaciones, cambiar turnos, marcar quién ya expuso y exportar asistentes a CSV. Los horarios estimados comienzan a las 18:30 y suman 20 minutos de presentación + 5 a 10 minutos de debate; no incluyen cena ni pausas.

## Para los invitados

- Registra nombre, email y tema; el archivo es opcional para confirmar asistencia.
- Guarda la clave privada que muestra la app. Usa esa clave y tu correo en **Mi expediente** para editar tus datos o reemplazar tu presentación. Un correo ya registrado no se puede sobrescribir sin la clave.
- PDF y Keynote (`.key`), máximo 50 MB. Si Keynote se guarda como carpeta o en un formato antiguo, expórtalo a PDF.
- Las cargas cierran el **23 de octubre de 2026 a las 12:00 p.m., zona America/Mexico_City**. El registro y las ediciones de tema siguen disponibles.
- La cartelera muestra nombre, tema y estado; correos y archivos quedan en el acceso del organizador.
- Subir un archivo **no envía un correo**. La invitación también permite enviarlo por tu cuenta a Alejandro.

## Supabase

La app ya tiene integración con Supabase por HTTPS, sin necesitar la contraseña de PostgreSQL ni conexión directa IPv6. Usa una tabla para los asistentes y metadatos de los archivos, y Supabase Storage para las presentaciones.

1. En tu proyecto, abre **SQL Editor**, pega el contenido de `supabase/setup.sql` y pulsa **Run**. Crea `diapocalipsis_guests`, un bucket privado `presentaciones` de 50 MB y la validación de fecha límite del lado de PostgreSQL. No concede acceso a `anon` ni `authenticated`; Streamlit controla el acceso con las claves de cada expediente y el acceso del organizador.
2. En **Project Settings → API Keys**, genera una Secret API key y guárdala **solo** en `.streamlit/secrets.toml`:

   ```toml
   SUPABASE_URL = "https://fdbvlbxgweedtssslqco.supabase.co"
   SUPABASE_SECRET_KEY = "sb_secret_TU_CLAVE_NUEVA"
   SUPABASE_STORAGE_BUCKET = "presentaciones"
   ```

   Conserva `ADMIN_PASSWORD`. Si compartiste una clave en un chat o captura, revócala y usa una nueva. La clave secreta debe permanecer en el servidor; no se publica en Git ni se envía al navegador de los invitados.
3. Ejecuta `python3 scripts/check_supabase.py`. Esta comprobación solo lee y confirma la tabla y el bucket privado. Recarga la app.

La URL de este proyecto ya está configurada localmente; falta una clave nueva y ejecutar el SQL. Mientras la configuración esté incompleta, la app muestra el pendiente y no registra asistentes en otra base por accidente. Las pruebas locales usan respuestas simuladas para los casos de Supabase; la conexión real requiere completar estos pasos.

La tabla guarda solo el hash de la clave del invitado. Correos, claves y presentaciones no tienen acceso público. Cada nueva carga usa una ruta aleatoria: al reemplazar un archivo se conserva su versión anterior privada para evitar perder evidencia ante fallos o cargas simultáneas. Los archivos sin referencia que queden por una respuesta de red incierta pueden revisarse manualmente en Storage; nunca se eliminan automáticamente tras un timeout.

El nombre del bucket del SQL es `presentaciones`; si lo cambias, cambia también `SUPABASE_STORAGE_BUCKET`. Los archivos subidos se guardan en Supabase y no se envían automáticamente al correo del organizador.

Referencias: [API REST de Supabase](https://supabase.com/docs/guides/api), [claves de servidor](https://supabase.com/docs/guides/getting-started/api-keys), [buckets privados](https://supabase.com/docs/guides/storage/buckets/fundamentals).

## Modo local

Cuando no configuras ni `SUPABASE_URL` ni `SUPABASE_SECRET_KEY`, la app usa SQLite y guarda registros y archivos en `data/expedientes.sqlite3`, excluido de Git. `DIAPOCALIPSIS_DATA_DIR` permite cambiar la carpeta. Respáldala para conservar todo. No se migran registros locales a Supabase automáticamente.

Las fuentes Bodoni Moda, Cormorant Garamond y DM Sans se cargan desde Google Fonts, con fuentes locales de respaldo si no hay conexión. La invitación está incluida y funciona sin conexión.

## Verificación

```bash
python3 -m unittest discover -s tests -v
```
