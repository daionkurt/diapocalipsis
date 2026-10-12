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

- Registra nombre, email y tema dentro de un único formulario; el archivo es opcional para confirmar asistencia. Solo se permite un registro por correo, ignorando mayúsculas y espacios al inicio o final.
- Guarda tu clave corta, con un formato como `luna-ovni-4826`. Usa esa clave y tu correo en **Mi expediente** para consultar tu entrega o completar tus datos antes de entregar. Las claves largas anteriores siguen funcionando. Las claves nuevas aceptan mayúsculas y minúsculas.
- PDF (`.pdf`), Keynote (`.key`), PowerPoint (`.pptx`), Word (`.doc`/`.docx`) y texto (`.txt`), máximo 50 MB. Si Keynote se guarda como carpeta o en un formato antiguo, expórtalo a PDF.
- Las cargas cierran el **23 de octubre de 2026 a las 5:00 p.m.**. Puedes registrarte sin archivo y completar el expediente después; una vez entregado el documento, el expediente queda confirmado y se ocultan los formularios.
- Solo se acepta **un documento por correo**, incluso si vuelves a abrir la app o intentas cambiar de correo después de la entrega. Al terminar, verás la confirmación y el nombre del archivo en lugar del formulario.
- El Protocolo de Seguridad aparece únicamente cuando eliges un archivo y confirmas el formulario: debes aceptar su casilla antes de la entrega definitiva. Sin archivo no se muestra.
- En **Mi expediente** puedes leer tu PDF o TXT y descargar el archivo original. DOCX y PPTX muestran el texto; Keynote muestra su vista previa incluida si existe. Word DOC y las presentaciones completas se abren descargando el archivo. Las vistas no envían documentos a servicios externos.
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

   Conserva `ADMIN_PASSWORD`. En Streamlit Cloud, guarda estos valores en **App settings → Secrets**; el archivo local no se debe subir a Git. Si compartiste una clave en un chat o captura, revócala y usa una nueva. La clave secreta debe permanecer en el servidor; no se publica en Git ni se envía al navegador de los invitados.
3. Ejecuta `python3 scripts/check_supabase.py`. Esta comprobación solo lee y confirma la tabla y el bucket privado. Recarga la app.

La URL de este proyecto ya está configurada localmente. Mientras la configuración esté incompleta, la app muestra el pendiente y no registra asistentes en otra base por accidente. Las pruebas locales usan respuestas simuladas para los casos de Supabase; `scripts/check_supabase.py` verifica la conexión real sin mostrar claves ni datos de invitados.

Si ya ejecutaste el SQL anterior, ejecuta `python3 scripts/update_supabase_formats.py` para agregar los nuevos formatos al bucket por API, o usa `supabase/update_formats.sql` en SQL Editor. En instalaciones nuevas, `setup.sql` ya incluye todos los formatos. El campo de categoría antiguo se conserva internamente por compatibilidad, pero ya no se solicita, muestra ni exporta.

La tabla guarda solo el hash de la clave del invitado. Correos, claves y presentaciones no tienen acceso público. Cada carga usa una ruta aleatoria. La app verifica el correo antes de cargar y actualiza solo expedientes sin documento, para impedir que dos entregas simultáneas sobrescriban evidencia. La protección adicional `supabase/lock_submissions.sql` bloquea cambiar un archivo ya recibido o reasignar su correo desde PostgreSQL; `setup.sql` ya la incluye para instalaciones nuevas. Los archivos sin referencia que queden por una respuesta de red incierta pueden revisarse manualmente en Storage; nunca se eliminan automáticamente tras un timeout.

El nombre del bucket del SQL es `presentaciones`; si lo cambias, cambia también `SUPABASE_STORAGE_BUCKET`. Los archivos subidos se guardan en Supabase y no se envían automáticamente al correo del organizador.

Referencias: [API REST de Supabase](https://supabase.com/docs/guides/api), [claves de servidor](https://supabase.com/docs/guides/getting-started/api-keys), [buckets privados](https://supabase.com/docs/guides/storage/buckets/fundamentals).

## Modo local

Supabase es la base predeterminada, también en Streamlit Cloud mediante `st.secrets`. Si faltan claves, la app muestra el error y no cambia automáticamente de base. Para usar el modo local de forma explícita, configura `STORAGE_BACKEND = "sqlite"`. En ese modo la app usa SQLite y guarda registros y archivos en `data/expedientes.sqlite3`, excluido de Git. `DIAPOCALIPSIS_DATA_DIR` permite cambiar la carpeta. Respáldala para conservar todo. No se migran registros locales a Supabase automáticamente.

Las fuentes Bodoni Moda, Cormorant Garamond y DM Sans se cargan desde Google Fonts, con fuentes locales de respaldo si no hay conexión. La ilustración original está incluida y funciona sin conexión; la portada muestra su parte artística y los detalles descargables reflejan el horario vigente.

## Verificación

```bash
python3 -m unittest discover -s tests -v
```

## Olvidé mi clave

En **Mi expediente → Olvidé mi clave**, el invitado solicita un código y después lo escribe para obtener una nueva clave corta. El código vence en 15 minutos, se usa una vez y se bloquea tras cinco intentos fallidos. Solicitarlo no invalida la clave actual; completar la recuperación sí. El documento y el bloqueo de una entrega por correo se conservan.

Para un proyecto ya creado, ejecuta `supabase/recovery.sql` y `supabase/update_deadline.sql` en SQL Editor. `setup.sql` incluye ambos cambios para proyectos nuevos.

Sin servicio de correo, la solicitud aparece en **Organizador → Recuperación de claves**. El organizador verifica la identidad, genera el código y lo comparte por privado. La app nunca revela la clave por conocer únicamente el email.

Para envío automático con Resend, verifica un dominio remitente y agrega en los secretos de Streamlit Cloud (y localmente si corresponde):

```toml
RESEND_API_KEY = "re_TU_CLAVE_PRIVADA"
RESEND_FROM = "Diapocalipsis <expedientes@tu-dominio.com>"
```

No se necesita SMTP. La API key permanece en el servidor. Mientras estos valores estén vacíos, la recuperación sigue disponible mediante el organizador. Los envíos automáticos se prueban con un transporte simulado; la entrega real requiere configurar Resend.

Referencias: [API de envío de Resend](https://resend.com/docs/api-reference/emails/send-email), [verificación del dominio](https://resend.com/docs/dashboard/domains/introduction).
