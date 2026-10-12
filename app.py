from datetime import datetime, timedelta
from html import escape
from pathlib import Path
import csv
import io
import secrets
import sqlite3

import streamlit as st
import storage
from settings import setting
from document_preview import show_document

ROOT = Path(__file__).parent
SAFETY_PROTOCOL = (
    "**⚠️ Protocolo de Seguridad:**\n\n"
    "Para mantener un ambiente seguro, si tu tema toca violencia gráfica, "
    "situaciones de riesgo con animales, pdf, homofobia, racismo, adicciones "
    "o jumpscares, menciónalos solo superficialmente para dar contexto. "
    "Evita las descripciones detalladas o imágenes gráficas."
)
st.set_page_config(page_title="Diapocalipsis · El contacto", page_icon="👁️", layout="wide")
st.markdown(f"<style>{(ROOT / 'assets/style.css').read_text()}</style>", unsafe_allow_html=True)


def html(text):
    st.markdown(text, unsafe_allow_html=True)


def secret_setting(key):
    return setting(key)


def upload_tuple(upload):
    return (upload.name, upload.getvalue()) if upload is not None else None


def submission_confirmation(guest, token=None):
    filename = storage.evidence_name(guest["id"])
    if filename:
        st.success("Ya subiste tu documento. Tu evidencia está recibida.")
        st.write(f"Archivo: {filename}")
        st.caption("Aceptamos un solo documento por correo. No necesitas volver a enviarlo.")
    else:
        st.success("Asistencia confirmada. Tu expediente ya está abierto.")
        st.info("Tu documento sigue pendiente. Entrégalo desde Mi expediente con tu correo y clave.")
    st.write(f'Tema: {guest["topic"]}')
    if token:
        st.markdown("**Guarda tu clave privada** para consultar tu expediente o entregar el documento pendiente.")
        st.code(token, language=None)
        st.download_button("Guardar mi clave", f"DIAPOCALIPSIS · Clave privada\n{token}\n\nUsa tu correo y esta clave en Mi expediente.\n", file_name="mi-clave-diapocalipsis.txt", mime="text/plain")


def existing_registration(email):
    status = storage.registration_status(email)
    if status["submitted"]:
        st.success("Este correo ya subió un documento. Tu evidencia ya está recibida.")
        st.caption("Aceptamos un solo documento por correo. Puedes consultar el expediente con tu clave en Mi expediente.")
    else:
        st.info("Este correo ya está registrado. Abre Mi expediente con tu clave para entregar tu documento pendiente.")
    if st.button("Usar otro correo"):
        st.session_state.pop("blocked_email", None)
        st.session_state.pop("registration_email", None)
        st.rerun()


def review_document(pending):
    st.subheader("Confirma tu documento")
    st.write(f'Archivo: {pending["upload"][0]}')
    st.caption("Una sola entrega por correo. Revisa el archivo antes de enviarlo.")
    with st.form("review_" + pending["action"]):
        st.warning(SAFETY_PROTOCOL)
        accepted = st.checkbox("Leí y acepto el Protocolo de Seguridad.")
        confirm = st.form_submit_button("Enviar mi documento", type="primary", width="stretch")
    if st.button("Volver al formulario", key="cancel_" + pending["action"]):
        st.session_state.pop("pending_document", None)
        st.rerun()
    if not confirm:
        return
    if not accepted:
        st.error("Acepta el Protocolo de Seguridad para entregar tu documento.")
        return
    try:
        if pending["action"] == "register":
            token = storage.register(pending["name"], pending["email"], pending["topic"], pending["upload"])
        else:
            token = pending["token"]
            storage.update(pending["id"], token, pending["name"], pending["email"], pending["topic"], pending["upload"])
    except (storage.AlreadySubmittedError, storage.AlreadyRegisteredError):
        st.session_state.pop("pending_document", None)
        if pending["action"] == "register":
            st.session_state.blocked_email = pending["email"]
        st.rerun()
    except (ValueError, storage.StorageError) as exc:
        st.error(str(exc))
    except (OSError, sqlite3.Error):
        st.error("No pudimos guardar tu documento. Intenta de nuevo.")
    else:
        st.session_state.pop("pending_document", None)
        st.session_state.receipt = token
        st.session_state.receipt_email = pending["email"]
        if pending["action"] == "update":
            st.session_state.guest_access = (pending["id"], token, pending["email"])
        st.rerun()


def register_form():
    pending = st.session_state.get("pending_document")
    if pending and pending["action"] == "register":
        review_document(pending)
        return
    if st.session_state.get("blocked_email"):
        existing_registration(st.session_state.blocked_email)
        return
    receipt_email = st.session_state.get("receipt_email")
    token = st.session_state.get("receipt")
    if receipt_email and token:
        guest = storage.lookup(receipt_email, token)
        if guest:
            submission_confirmation(guest, token)
            if st.button("Registrar a otra persona"):
                for key in ("receipt", "receipt_email", "guest_access", "registration_email"):
                    st.session_state.pop(key, None)
                st.rerun()
            return
    st.subheader("Abre tu expediente")
    html('<div class="section-note">Toda teoría necesita un testigo. Confirma tu asistencia y cuéntanos qué vas a revelar.</div>')
    with st.form("registration", clear_on_submit=False):
        left, right = st.columns(2)
        name = left.text_input("Tu nombre", placeholder="¿Quién está detrás de la teoría?", max_chars=80)
        email = right.text_input("Tu correo", placeholder="nombre@correo.com", max_chars=254, key="registration_email")
        topic = st.text_input("El tema de tu presentación", placeholder="Ej. ¿Y si la Luna es una estación espacial?", max_chars=160)
        upload = st.file_uploader("Tu documento · PDF, KEY, PPTX, Word o TXT", type=storage.ALLOWED_EXTENSIONS, disabled=datetime.now(storage.TZ) >= storage.DEADLINE,
                                  help="Hasta 50 MB. Un solo documento por correo. Para Keynote usa un archivo .key; si tu Mac lo guarda como carpeta, exporta a PDF.")
        st.caption("Puedes registrarte ahora y subir tu presentación después con tu clave. Recepción hasta el 23 de octubre de 2026, 12:00 p.m. (Ciudad de México).")
        consent = st.checkbox("Acepto que mi nombre y tema aparezcan en la cartelera; mi correo y archivo serán visibles para el organizador.")
        submitted = st.form_submit_button("Confirmar mi asistencia  →", type="primary", width="stretch")
    if submitted:
        try:
            email = storage.normalize_email(email)
            status = storage.registration_status(email)
            if status["registered"]:
                st.session_state.blocked_email = email
                st.rerun()
            if not consent:
                st.error("Confirma que aceptas aparecer en la cartelera para abrir tu expediente.")
                return
            name, email, topic = storage.validate_fields(name, email, topic)
            evidence = upload_tuple(upload)
            if evidence:
                storage.validate_evidence(*evidence)
                st.session_state.pending_document = {"action": "register", "name": name, "email": email, "topic": topic, "upload": evidence}
                st.rerun()
            token = storage.register(name, email, topic)
        except (storage.AlreadySubmittedError, storage.AlreadyRegisteredError):
            st.session_state.blocked_email = email
            st.rerun()
        except (ValueError, storage.StorageError) as exc:
            st.error(str(exc))
        except (OSError, sqlite3.Error):
            st.error("No pudimos guardar el expediente. Intenta de nuevo o contacta al organizador.")
        else:
            st.session_state.receipt = token
            st.session_state.receipt_email = email
            st.rerun()


def my_dossier():
    st.subheader("Tu evidencia, bajo llave")
    pending = st.session_state.get("pending_document")
    if pending and pending["action"] == "update":
        review_document(pending)
        return
    if st.session_state.pop("edited_success", False):
        st.success("Expediente actualizado.")
    access = st.session_state.get("guest_access")
    if not access:
        st.caption("Usa el correo y la clave privada que recibiste al confirmar tu asistencia.")
        with st.form("access"):
            email = st.text_input("Correo del expediente")
            token = st.text_input("Clave privada", type="password")
            submit = st.form_submit_button("Abrir mi expediente")
        if submit:
            guest = storage.lookup(email, token)
            if guest:
                st.session_state.guest_access = (guest["id"], token, email.strip().lower())
                st.rerun()
            else:
                st.error("Correo o clave incorrectos. Si perdiste tu clave, contacta a Alejandro.")
        return
    guest = storage.lookup(access[2], access[1])
    if not guest:
        st.session_state.pop("guest_access", None)
        st.rerun()
    existing = storage.evidence_name(guest["id"])
    if existing:
        submission_confirmation(guest)
        file = storage.evidence(guest["id"])
        if file:
            show_document(file[0], file[1], guest["id"])
    else:
        st.info("Tu lugar está confirmado. Tu documento sigue pendiente.")
        with st.form("edit_guest"):
            name = st.text_input("Nombre", value=guest["name"], max_chars=80)
            new_email = st.text_input("Correo", value=guest["email"], max_chars=254)
            topic = st.text_input("Tema", value=guest["topic"], max_chars=160)
            upload = st.file_uploader("Entregar mi documento", type=storage.ALLOWED_EXTENSIONS, disabled=datetime.now(storage.TZ) >= storage.DEADLINE)
            st.caption("Una sola entrega por correo. Revisa tu documento antes de enviarlo.")
            save = st.form_submit_button("Guardar expediente", type="primary")
        if save:
            try:
                name, new_email, topic = storage.validate_fields(name, new_email, topic)
                evidence = upload_tuple(upload)
                if evidence:
                    storage.validate_evidence(*evidence)
                    st.session_state.pending_document = {"action": "update", "id": guest["id"], "token": access[1], "name": name, "email": new_email, "topic": topic, "upload": evidence}
                    st.rerun()
                storage.update(guest["id"], access[1], name, new_email, topic)
            except storage.AlreadySubmittedError:
                st.rerun()
            except (ValueError, storage.StorageError) as exc:
                st.error(str(exc))
            except (OSError, sqlite3.Error):
                st.error("No pudimos guardar los cambios. Intenta de nuevo.")
            else:
                st.session_state.guest_access = (guest["id"], access[1], new_email)
                st.session_state.receipt_email = new_email
                st.session_state.receipt = access[1]
                st.session_state.edited_success = True
                st.rerun()
    if st.button("Cerrar mi expediente"):
        st.session_state.pop("guest_access", None)
        st.rerun()


def lineup(rows):
    st.subheader("La cartelera de lo inexplicable")
    html('<div class="section-note">Una noche. Muchas teorías. Ve descubriendo quiénes traerán las pruebas.</div>')
    if not rows:
        st.info("Aún no hay expedientes aquí. El próximo misterio puede ser el tuyo.")
    for row in rows:
        state = "Caso expuesto" if row["presented"] else "Evidencia recibida" if row["filename"] else "Evidencia pendiente"
        html(f'<div class="dossier"><div class="meta">EXP. {row["id"]:03d}</div><h3>{escape(row["topic"])}</h3><div class="who">{escape(row["name"])} &nbsp; / &nbsp; {state}</div></div>')
    st.caption("El orden de exposición se confirma con el organizador. 20 minutos de presentación + 5 a 10 minutos de debate por expediente.")


def invitation():
    st.subheader("Expediente confidencial")
    cards = [
        ("◷", "El contacto", "Viernes 23 de octubre de 2026.<br>A partir de las 6:30 p.m."),
        ("⌖", "Coordenadas", "Av. Guadalupe #5511, Int. B15.<br>Puedes dejar tu nave/coche en la gasolinera de enfrente."),
        ("◴", "La dinámica", "20 minutos exactos para exponer.<br>5 a 10 minutos de debate y preguntas."),
        ("♧", "Menú del terror", "Bebidas, botana y cena terroríficas para sobrevivir a la noche."),
        ("♜", "El outfit", "Un look relacionado a tu tema o a tu película de terror favorita. Un sombrero o gorro de aluminio también cuenta."),
        ("✉", "Recepción de evidencia", "PDF, Keynote, PowerPoint (.pptx), Word (.doc/.docx) o TXT, a más tardar el viernes 23 a las 12:00 p.m. Sube tu archivo aquí o envíalo a alejandrofls@icloud.com."),
    ]
    for start in (0, 3):
        columns = st.columns(3)
        for col, (symbol, title, description) in zip(columns, cards[start:start + 3]):
            with col:
                html(f'<div class="info-card"><div class="symbol">{symbol}</div><h3>{title}</h3><p>{description}</p></div>')
    st.link_button("Abrir correo de Alejandro", "mailto:alejandrofls@icloud.com")
    st.caption("Las cargas de esta app se guardan para el organizador; no se envían automáticamente por correo.")
    st.download_button("Guardar la invitación", (ROOT / "assets/invitacion.png").read_bytes(), file_name="diapocalipsis-invitacion.png", mime="image/png")


def organizer(rows):
    password = secret_setting("ADMIN_PASSWORD")
    if not password or password == "replace-with-a-long-private-password":
        st.info("El acceso del organizador todavía no está configurado. Consulta el README para activar tu clave privada.")
        return
    authenticated = st.session_state.get("admin_authenticated", False)
    if not authenticated:
        st.subheader("Acceso restringido")
        with st.form("admin_login"):
            entered = st.text_input("Clave del organizador", type="password")
            submitted = st.form_submit_button("Entrar al archivo")
        if submitted:
            if secrets.compare_digest(entered, password):
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("Clave incorrecta.")
        return
    st.subheader("Control de la noche")
    if st.button("Cerrar sesión del organizador"):
        st.session_state.admin_authenticated = False
        st.rerun()
    if not rows:
        st.info("Los registros aparecerán aquí cuando alguien confirme su asistencia.")
        return
    st.caption("Cambia el número de turno para ordenar las exposiciones. Si dos turnos coinciden, se usa el orden de registro.")
    debate = st.slider("Minutos de debate por presentación", 5, 10, 10)
    for i, row in enumerate(rows):
        when = storage.EVENT + timedelta(minutes=i * (20 + debate))
        with st.expander(f'{i + 1:02d} · {when.strftime("%H:%M")} · {row["name"]} — {row["topic"]}'):
            st.write(f'Correo: {row["email"]}')
            st.caption("Horario estimado, sin incluir pausas ni cena.")
            with st.form(f'order_{row["id"]}'):
                position = st.number_input("Turno", min_value=1, value=row["position"], step=1)
                presented = st.checkbox("Ya expuso", value=bool(row["presented"]))
                if st.form_submit_button("Actualizar turno"):
                    storage.organize(row["id"], position, presented)
                    st.rerun()
            if row["filename"]:
                file = storage.evidence(row["id"])
                st.download_button("Descargar evidencia", file[1], file_name=file[0], key=f'download_{row["id"]}', mime=storage.content_type(file[0]))
            else:
                st.warning("Presentación pendiente.")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Turno", "Nombre", "Email", "Tema", "Archivo", "Expuso"])
    for row in rows:
        # Prevent spreadsheet formula execution in user-provided cells.
        cells = [row["position"], row["name"], row["email"], row["topic"], row["filename"] or "Pendiente", "Sí" if row["presented"] else "No"]
        writer.writerow(["'" + c if isinstance(c, str) and c.lstrip().startswith(("=", "+", "-", "@")) else c for c in cells])
    st.download_button("Exportar lista de asistentes · CSV", output.getvalue().encode("utf-8-sig"), file_name="diapocalipsis-asistentes.csv", mime="text/csv")


html('<div class="topline"><strong>◈ &nbsp; DIAPOCALIPSIS</strong><span>ARCHIVO CONFIDENCIAL &nbsp; / &nbsp; 23.10.2026</span></div>')
left, right = st.columns([1.45, 0.75], gap="large")
with left:
    html('<div class="kicker">Una noche de diapositivas y secretos</div><div class="hero-title">La verdad está<em>ahí fuera.</em></div><p class="hero-sub">Teorías conspirativas, sucesos paranormales y seres de otros mundos.</p><p class="hero-small">Ha llegado el momento de revelar los secretos mejor guardados. Reúne tus pruebas, prepara tus diapositivas y ven a defender lo inexplicable.</p><div class="seal">EL DIAPOCALIPSIS LLEGÓ</div>')
    st.caption("VIERNES 23 DE OCTUBRE · 6:30 P.M. · AV. GUADALUPE #5511, INT. B15")
    now = datetime.now(storage.TZ)
    if now < storage.EVENT:
        delta = storage.EVENT - now
        st.caption(f"EL CONTACTO EN {delta.days} DÍAS Y {delta.seconds // 3600} HORAS")
    else:
        st.caption("TE LO ADVERTIMOS: DESPUÉS DE ESTA NOCHE, NADA SERÁ IGUAL.")
with right:
    st.image(str(ROOT / "assets/invitacion.png"), width=300)

try:
    rows = storage.guests()
except storage.StorageError as exc:
    st.error(str(exc))
    st.info("Completa la configuración de Supabase y ejecuta supabase/setup.sql en SQL Editor. Después recarga esta página.")
    st.stop()
except (OSError, sqlite3.Error):
    st.error("No podemos abrir el archivo de expedientes. Revisa el almacenamiento de la app.")
    st.stop()
ready = sum(bool(r["filename"]) for r in rows)
for col, value, label in zip(st.columns(3), [f"{len(rows):02d}", f"{ready:02d}", "20 + 10"], ["Testigos confirmados", "Evidencias recibidas", "Minutos por expediente"]):
    with col:
        html(f'<div class="stat"><b>{value}</b><span>{label}</span></div>')
registration, personal, board, info, admin = st.tabs(["01 / Confirmar", "02 / Mi expediente", "03 / Cartelera", "04 / La noche", "⌑ Organizador"])
with registration:
    try:
        register_form()
    except storage.StorageError as exc:
        st.error(str(exc))
with personal:
    try:
        my_dossier()
    except storage.StorageError as exc:
        st.error(str(exc))
with board:
    lineup(rows)
with info:
    invitation()
with admin:
    try:
        organizer(rows)
    except storage.StorageError as exc:
        st.error(str(exc))
html('<div class="footer">◈ &nbsp; PREPARA TUS PRUEBAS. LA VERDAD ESTÁ AHÍ FUERA. &nbsp; ◈</div>')
