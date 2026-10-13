from datetime import datetime, timedelta
from html import escape
from pathlib import Path
import csv
import io
import secrets
import sqlite3
import time

import streamlit as st
import storage
import recovery
import roulette
import streamlit.components.v1 as components
from settings import setting
from document_preview import download_document

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
if not st.session_state.get("intro_seen"):
    st.session_state.intro_seen = True
    st.html((ROOT / "assets/contact-intro.html").read_text())


def html(text):
    st.markdown(text, unsafe_allow_html=True)


def secret_setting(key):
    return setting(key)


def cached_rows():
    cached = st.session_state.get("guest_rows_cache")
    if cached and time.monotonic() - cached["at"] < 5:
        return cached["rows"]
    rows = storage.guests()
    st.session_state.guest_rows_cache = {"at": time.monotonic(), "rows": rows}
    return rows


def invalidate_rows():
    st.session_state.pop("guest_rows_cache", None)


def upload_tuple(upload):
    return (upload.name, upload.getvalue()) if upload is not None else None


def submission_confirmation(guest, token=None):
    filename = guest["filename"] if "filename" in guest else storage.evidence_name(guest["id"])
    if filename:
        st.success("Ya subiste tu documento. Tu evidencia está recibida.")
        st.write(f"Archivo: {filename}")
        st.caption("Solo puede haber un documento activo por correo. Puedes eliminarlo desde Mi expediente para subir otro.")
    elif not storage.is_presenter(guest):
        st.success("¡Asistencia confirmada! Nos vemos en el Diapocalipsis.")
        st.caption("Vienes como invitado. No necesitas subir un documento.")
    else:
        st.success("Asistencia confirmada. Tu expediente ya está abierto.")
        st.info("Tu documento sigue pendiente. Entrégalo desde Mi expediente con tu correo y clave.")
    if storage.is_presenter(guest):
        st.write(f'Tema: {guest["topic"]}')
    if token:
        st.markdown("**Guarda tu clave privada** para consultar tu expediente.")
        st.code(token, language=None)
        st.download_button("Guardar mi clave", f"DIAPOCALIPSIS · Clave privada\n{token}\n\nUsa tu correo y esta clave en Mi expediente.\n", file_name="mi-clave-diapocalipsis.txt", mime="text/plain")


def existing_registration(email):
    status = storage.registration_status(email)
    if status["submitted"]:
        st.success("Este correo ya subió un documento. Tu evidencia ya está recibida.")
        st.caption("Solo puede haber un documento activo por correo. Abre Mi expediente con tu clave para consultarlo o eliminarlo.")
    else:
        st.info("Este correo ya confirmó su asistencia. Puedes consultar tu expediente con tu clave.")
    if st.button("Usar otro correo"):
        st.session_state.pop("blocked_email", None)
        st.session_state.pop("registration_email", None)
        st.rerun()


def review_document(pending):
    st.subheader("Confirma tu documento")
    st.write(f'Archivo: {pending["upload"][0]}')
    st.caption("Una sola entrega por correo. Revisa el archivo antes de enviarlo.")
    with st.form("review_" + pending["action"], enter_to_submit=False):
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
            with st.spinner("Registrando y subiendo tu archivo secreto…", show_time=True):
                token = storage.register(pending["name"], pending["email"], pending["topic"], pending["upload"], presenting=pending.get("presenting", True))
        else:
            token = pending["token"]
            with st.spinner("Subiendo tu archivo secreto…", show_time=True):
                storage.update(pending["id"], token, pending["name"], pending["email"], pending["topic"], pending["upload"], presenting=pending.get("presenting", True))
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
        invalidate_rows()
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
                for key in ("receipt", "receipt_email", "guest_access", "registration_email", "wants_to_present"):
                    st.session_state.pop(key, None)
                st.rerun()
            return
    st.subheader("Abre tu expediente")
    html('<div class="section-note">Toda teoría necesita un testigo. Confirma tu asistencia y elige si quieres presentar.</div>')
    presenting = st.checkbox("Quiero presentar", key="wants_to_present")
    with st.container(key="registration_panel"):
        with st.form("registration", clear_on_submit=False, enter_to_submit=False):
            left, right = st.columns(2)
            name = left.text_input("Tu nombre", placeholder="¿Quién está detrás de la teoría?", max_chars=80)
            email = right.text_input("Tu correo", placeholder="nombre@correo.com", max_chars=254, key="registration_email")
            topic, upload = "Solo asistencia", None
            if presenting:
                topic = st.text_input("El tema de tu presentación", placeholder="Ej. ¿Y si la Luna es una estación espacial?", max_chars=160)
                upload = st.file_uploader("Tu documento", disabled=datetime.now(storage.TZ) >= storage.DEADLINE,
                                          help="Hasta 50 MB. Un solo documento por correo.")
                st.caption("Puedes registrarte ahora y subir tu presentación después con tu clave. Recepción hasta el 23 de octubre de 2026, 5:00 p.m..")
            consent_label = ("Acepto que mi nombre y tema aparezcan en la cartelera; mi correo y archivo serán visibles para el organizador." if presenting else "Acepto que mi nombre aparezca en la cartelera; mi correo será visible para el organizador.")
            consent = st.checkbox(consent_label)
            submitted = st.form_submit_button("Confirmar mi asistencia  →", type="primary", width="stretch")
    if submitted:
        with st.spinner("Registrando tu asistencia…", show_time=True):
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
                token = storage.register(name, email, topic, presenting=presenting)
            except (storage.AlreadySubmittedError, storage.AlreadyRegisteredError):
                st.session_state.blocked_email = email
                st.rerun()
            except (ValueError, storage.StorageError) as exc:
                st.error(str(exc))
            except (OSError, sqlite3.Error):
                st.error("No pudimos guardar el expediente. Intenta de nuevo o contacta al organizador.")
            else:
                invalidate_rows()
                st.session_state.receipt = token
                st.session_state.receipt_email = email
                st.rerun()


def forgot_key():
    with st.expander("Olvidé mi clave"):
        st.caption("Recupera el acceso con un código de un solo uso. Tu documento se conserva.")
        with st.form("recovery_request"):
            email = st.text_input("Correo para recuperar el expediente", max_chars=254)
            requested = st.form_submit_button("Solicitar código de recuperación")
        if requested:
            try:
                automatic = recovery.request_recovery(email)
            except (ValueError, storage.StorageError) as exc:
                st.error(str(exc))
            else:
                if automatic:
                    st.info("Si el correo está registrado, recibirás un código. Si ya solicitaste uno recientemente, usa el último; vence en 15 minutos.")
                else:
                    st.info("Si el correo está registrado, tu solicitud quedó en el panel del organizador. Pídele tu código por privado y escríbelo aquí.")
        with st.form("recovery_finish"):
            recovery_email = st.text_input("Correo de tu expediente", max_chars=254)
            code = st.text_input("Código de recuperación", max_chars=8, placeholder="Código de 8 dígitos")
            confirmed = st.form_submit_button("Recuperar mi clave", type="primary")
        if confirmed:
            try:
                new_key = recovery.finish(recovery_email, code)
                st.session_state.recovered_key = new_key
                st.session_state.receipt = new_key
                st.session_state.receipt_email = recovery_email.strip().lower()
                guest = storage.lookup(recovery_email, new_key)
            except (ValueError, storage.StorageError) as exc:
                st.error(str(exc))
                if st.session_state.get("recovered_key"):
                    st.code(st.session_state.recovered_key, language=None)
            else:
                if not guest:
                    st.warning("Tu clave se recuperó. Guarda la nueva clave y úsala para abrir tu expediente.")
                    st.code(new_key, language=None)
                    return
                st.session_state.recovered_key = new_key
                st.session_state.receipt = new_key
                st.session_state.receipt_email = guest["email"]
                st.session_state.guest_access = (guest["id"], new_key, guest["email"])
                st.rerun()


def remove_document(guest, token, filename):
    if st.button("Eliminar mi documento", key=f'remove_file_{guest["id"]}'):
        st.session_state.remove_document_id = guest["id"]
    if st.session_state.get("remove_document_id") != guest["id"]:
        return
    st.warning(f'¿Eliminar {filename}? Tu asistencia y clave se conservan. Podrás subir otro documento antes del cierre. Esta acción no se puede deshacer.')
    confirm, cancel = st.columns(2)
    if cancel.button("Conservar mi documento"):
        st.session_state.pop("remove_document_id", None)
        st.rerun()
    if confirm.button("Sí, eliminar documento", type="primary"):
        try:
            with st.spinner("Eliminando tu documento…", show_time=True):
                cleaned = storage.remove_evidence(guest["id"], token)
        except (ValueError, storage.StorageError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
        else:
            st.session_state.pop("remove_document_id", None)
            st.session_state.pop("pending_document", None)
            invalidate_rows()
            st.session_state.removed_document = cleaned
            st.rerun()


def organizer_recoveries():
    with st.expander("Recuperación de claves"):
        st.caption("Confirma que hablas con el titular del correo antes de compartirle un código por privado. Vence en 15 minutos y se usa una sola vez.")
        try:
            requests = recovery.pending_requests()
        except storage.StorageError:
            st.info("Para activar la recuperación, ejecuta supabase/recovery.sql en SQL Editor.")
            return
        if not requests:
            st.caption("No hay solicitudes de recuperación pendientes.")
        for request in requests:
            st.write(f'{request["name"]} · {request["email"]}')
            if st.button("Generar código de recuperación", key=f'recovery_issue_{request["guest_id"]}'):
                try:
                    code = recovery.organizer_code(request["email"])
                except (ValueError, storage.StorageError) as exc:
                    st.error(str(exc))
                else:
                    st.session_state.organizer_recovery_code = (request["email"], code)
            issued = st.session_state.get("organizer_recovery_code")
            if issued and issued[0] == request["email"]:
                st.code(issued[1], language=None)
                st.caption("Compártelo directamente con esta persona; no lo publiques en la cartelera.")


def my_dossier():
    st.subheader("Tu evidencia, bajo llave")
    if st.session_state.get("recovered_key"):
        st.success("Acceso recuperado. Guarda tu nueva clave; la anterior dejó de funcionar.")
        st.code(st.session_state.recovered_key, language=None)
    pending = st.session_state.get("pending_document")
    if pending and pending["action"] == "update":
        review_document(pending)
        return
    removed = st.session_state.pop("removed_document", None)
    if removed is True:
        st.success("Documento eliminado. El expediente queda listo para recibir tu nuevo archivo secreto.")
    elif removed is False:
        st.warning("El documento ya se retiró de tu expediente. No pudimos completar su borrado del almacenamiento; avisa al organizador para terminar la limpieza.")
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
                st.error("Correo o clave incorrectos. Puedes recuperar tu acceso en Olvidé mi clave.")
        forgot_key()
        return
    guest = storage.lookup(access[2], access[1])
    if not guest:
        st.session_state.pop("guest_access", None)
        st.rerun()
    existing = guest["filename"] if "filename" in guest else storage.evidence_name(guest["id"])
    presenting = st.checkbox("Quiero presentar", value=storage.is_presenter(guest), key=f'dossier_present_{guest["id"]}')
    if presenting != storage.is_presenter(guest):
        if presenting:
            st.info("¿Aaah, cambiando de opinión? El comité de conspiraciones te espera. Tu archivo secreto ya está listo." if existing else "¿Aaah, cambiando de opinión? Bien. Sube tu archivo secreto… el comité de conspiraciones te espera.")
        else:
            st.info("¿Prefieres investigar desde tu silla? Perfecto. Tu lugar sigue reservado; guarda el cambio y disfruta los secretos ajenos.")
    if existing:
        if presenting != storage.is_presenter(guest) and st.button("Guardar mi selección", type="primary"):
            try:
                with st.spinner("Guardando tu selección…", show_time=True):
                    storage.set_presenting(guest["id"], access[1], presenting)
            except (ValueError, storage.StorageError) as exc:
                st.error(str(exc))
            else:
                invalidate_rows()
                st.session_state.edited_success = True
                st.rerun()
        submission_confirmation(guest)
        download_document(existing, guest["id"], email=access[2], token=access[1])
        remove_document(guest, access[1], existing)
    else:
        if presenting == storage.is_presenter(guest):
            if presenting:
                st.info("Tu lugar está confirmado. Tu documento sigue pendiente.")
            else:
                st.success("Tu asistencia está confirmada. Vienes a escuchar los secretos.")
        with st.form("edit_guest", enter_to_submit=False):
            name = st.text_input("Nombre", value=guest["name"], max_chars=80)
            new_email = st.text_input("Correo", value=guest["email"], max_chars=254)
            topic, upload = "Solo asistencia", None
            if presenting:
                topic = st.text_input("Tema", value=guest["topic"] if storage.is_presenter(guest) else "", max_chars=160)
                upload = st.file_uploader("Entregar mi documento", disabled=datetime.now(storage.TZ) >= storage.DEADLINE)
                st.caption("Una sola entrega por correo. Revisa tu documento antes de enviarlo.")
            save = st.form_submit_button("Guardar expediente", type="primary")
        if save:
            try:
                name, new_email, topic = storage.validate_fields(name, new_email, topic)
                evidence = upload_tuple(upload)
                if evidence:
                    storage.validate_evidence(*evidence)
                    st.session_state.pending_document = {"action": "update", "id": guest["id"], "token": access[1], "name": name, "email": new_email, "topic": topic, "upload": evidence, "presenting": presenting}
                    st.rerun()
                with st.spinner("Guardando tu expediente…", show_time=True):
                    storage.update(guest["id"], access[1], name, new_email, topic, presenting=presenting)
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
                invalidate_rows()
                st.session_state.edited_success = True
                st.rerun()
    if st.button("Cerrar mi expediente"):
        st.session_state.pop(f'dossier_present_{guest["id"]}', None)
        for key in ("guest_access", "recovered_key", "receipt", "receipt_email", "remove_document_id"):
            st.session_state.pop(key, None)
        st.rerun()


def lineup(rows):
    st.subheader("La cartelera de lo inexplicable")
    html('<div class="section-note">Una noche. Muchas teorías. Ve descubriendo quiénes traerán las pruebas.</div>')
    if not rows:
        st.info("Aún no hay expedientes aquí. El próximo misterio puede ser el tuyo.")
    for row in rows:
        if not storage.is_presenter(row):
            html(f'<div class="dossier"><div class="meta">ASISTENCIA CONFIRMADA</div><h3>{escape(row["name"])}</h3><div class="who">Invitado · Sin presentación</div></div>')
            continue
        state = "Caso expuesto" if row["presented"] else "Evidencia recibida" if row["filename"] else "Evidencia pendiente"
        html(f'<div class="dossier"><div class="meta">EXP. {row["id"]:03d}</div><h3>{escape(row["topic"])}</h3><div class="who">{escape(row["name"])} &nbsp; / &nbsp; {state}</div></div>')
    st.caption("El orden de exposición se confirma con el organizador. 15 minutos de presentación + 5 minutos de preguntas por expediente.")


def invitation():
    st.subheader("Expediente confidencial")
    cards = [
        ("◷", "El contacto", "Viernes 23 de octubre de 2026.<br>A partir de las 6:30 p.m."),
        ("⌖", "Coordenadas", "Av. Guadalupe #5511, Int. B15.<br>Puedes dejar tu nave/coche en la gasolinera de enfrente."),
        ("◴", "La dinámica", "15 minutos exactos para exponer.<br>5 minutos de preguntas."),
        ("♧", "Menú del terror", "Bebidas, botana y cena terroríficas para sobrevivir a la noche."),
        ("♜", "El outfit", "Un look relacionado a tu tema o a tu película de terror favorita. Un sombrero o gorro de aluminio también cuenta."),
        ("✉", "Recepción de evidencia", "Tu documento, a más tardar el viernes 23 a las 5:00 p.m. Sube tu archivo aquí o envíalo a alejandrofls@icloud.com."),
    ]
    for start in (0, 3):
        columns = st.columns(3)
        for col, (symbol, title, description) in zip(columns, cards[start:start + 3]):
            with col:
                html(f'<div class="info-card"><div class="symbol">{symbol}</div><h3>{title}</h3><p>{description}</p></div>')
    st.link_button("Abrir correo de Alejandro", "mailto:alejandrofls@icloud.com")
    st.caption("Las cargas de esta app se guardan para el organizador; no se envían automáticamente por correo.")
    details = "DIAPOCALIPSIS\nViernes 23 de octubre de 2026, desde las 6:30 p.m.\nAv. Guadalupe #5511, Int. B15.\nRecepción de documentos hasta las 5:00 p.m. del viernes 23.\n15 minutos de presentación + 5 minutos de preguntas.\nBebidas, botana y cena. Ven con un look o accesorio relacionado con tu tema.\nContacto: alejandrofls@icloud.com\n"
    st.download_button("Guardar los detalles de la noche", details, file_name="diapocalipsis-detalles.txt", mime="text/plain")


def draw_investigation(options):
    try:
        picked = roulette.draw()
    except storage.StorageError as exc:
        st.session_state.roulette_error = str(exc)
    else:
        if picked is not None:
            if picked not in {row["id"] for row in options}:
                invalidate_rows()
            st.session_state.roulette_animation = picked
            st.session_state.roulette_previous_options = options


def reset_investigations():
    try:
        roulette.reset()
    except storage.StorageError as exc:
        st.session_state.roulette_error = str(exc)
    else:
        st.session_state.pop("roulette_animation", None)
        st.session_state.pop("roulette_previous_options", None)


@st.fragment
def investigations(admin_mode):
    rows = cached_rows()
    error = st.session_state.pop("roulette_error", None)
    if error:
        st.error(error)
    st.subheader("La ruleta de lo inexplicable")
    st.caption("Que el azar decida qué secreto sale a la luz. Solo participan quienes presentan y ya entregaron su documento.")
    candidates = roulette.eligible(rows)
    try:
        current = roulette.state()
    except storage.StorageError:
        st.info("La ruleta está pendiente de configuración. El organizador debe ejecutar supabase/roulette.sql.")
        return
    remaining = [r for r in candidates if r["id"] not in current["drawn"]]
    selected = next((r for r in candidates if r["id"] == current["selected"]), None)
    animation = st.session_state.pop("roulette_animation", None)
    display_rows = st.session_state.pop("roulette_previous_options", None) if animation else None
    wheel_col, result_col = st.columns([1, 1], gap="large")
    with wheel_col:
        components.html(roulette.wheel(display_rows or remaining, animation, bool(animation)), height=445)
    with result_col:
        st.caption(f"{len(remaining)} investigaciones pendientes · {len(current['drawn'])} expedientes sorteados")
        if remaining:
            with st.expander("Investigaciones disponibles"):
                for i, row in enumerate(remaining, 1):
                    st.write(f"{i:02d} · {row['name']} — {row['topic']}")
        draw_col, reset_col = st.columns(2)
        draw_col.button("Iniciar investigaciones 👁", type="primary", disabled=not remaining, width="stretch", on_click=draw_investigation, args=(remaining,))
        reset_col.button("Reiniciar toda la ruleta", disabled=not current["drawn"], width="stretch", on_click=reset_investigations)
        if not candidates:
            st.info("Aún no hay archivos secretos listos para investigar.")
        elif not remaining:
            st.success("Todos los secretos salieron a la luz. Reinicia la ruleta para otra ronda.")
        if selected:
            st.markdown(f"### Investigador elegido: {escape(selected['name'])}")
            st.write(f"Tema: {selected['topic']}")
            st.caption("15 minutos de presentación + 5 minutos de preguntas. Esta presentación ya salió de la ruleta.")
            if admin_mode and st.session_state.get("admin_authenticated"):
                download_document(selected["filename"], selected["id"], label="Descargar presentación elegida", key=f"roulette_download_{selected['id']}")
            else:
                st.caption("El organizador puede descargarla al abrir su acceso privado. El autor también puede abrirla desde Mi expediente.")
        if current["drawn"]:
            with st.expander("Investigaciones que ya salieron"):
                by_id = {r["id"]: r for r in candidates}
                for i, guest_id in enumerate(current["drawn"], 1):
                    row = by_id.get(guest_id)
                    st.write(f"{i:02d} · {row['name']} — {row['topic']}" if row else f"{i:02d} · Expediente retirado")


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
        st.session_state.pop("organizer_recovery_code", None)
        st.rerun()
    organizer_recoveries()
    if not rows:
        st.info("Los registros aparecerán aquí cuando alguien confirme su asistencia.")
        return
    st.caption("Cambia el número de turno para ordenar las exposiciones. Si dos turnos coinciden, se usa el orden de registro.")
    st.caption("Cada expediente: 15 minutos de presentación + 5 minutos de preguntas.")
    speakers = [r for r in rows if storage.is_presenter(r)]
    attendees = [r for r in rows if not storage.is_presenter(r)]
    if attendees:
        with st.expander(f"Invitados sin presentación · {len(attendees)}"):
            for row in attendees:
                st.write(f'{row["name"]} · {row["email"]}')
    for i, row in enumerate(speakers):
        when = storage.EVENT + timedelta(minutes=i * (15 + 5))
        with st.expander(f'{i + 1:02d} · {when.strftime("%H:%M")} · {row["name"]} — {row["topic"]}'):
            st.write(f'Correo: {row["email"]}')
            st.caption("Horario estimado, sin incluir pausas ni cena.")
            with st.form(f'order_{row["id"]}'):
                position = st.number_input("Turno", min_value=1, value=row["position"], step=1)
                presented = st.checkbox("Ya expuso", value=bool(row["presented"]))
                if st.form_submit_button("Actualizar turno"):
                    with st.spinner("Actualizando turno…", show_time=True):
                        storage.organize(row["id"], position, presented)
                    invalidate_rows()
                    st.rerun()
            if row["filename"]:
                download_document(row["filename"], row["id"], label="Descargar evidencia", key=f'download_{row["id"]}')
            else:
                st.warning("Presentación pendiente.")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Turno", "Nombre", "Email", "Tema", "Archivo", "Expuso"])
    for row in rows:
        # Prevent spreadsheet formula execution in user-provided cells.
        cells = [row["position"], row["name"], row["email"], row["topic"], row["filename"] or ("Pendiente" if storage.is_presenter(row) else "No aplica"), "Sí" if row["presented"] else "No"]
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
    with st.container(key="poster"):
        st.image(str(ROOT / "assets/invitacion.png"), width="stretch", output_format="PNG")

try:
    rows = cached_rows()
except storage.StorageError as exc:
    st.error(str(exc))
    st.info("Completa la configuración de Supabase y ejecuta supabase/setup.sql en SQL Editor. Después recarga esta página.")
    st.stop()
except (OSError, sqlite3.Error):
    st.error("No podemos abrir el archivo de expedientes. Revisa el almacenamiento de la app.")
    st.stop()
ready = sum(bool(r["filename"]) for r in rows)
for col, value, label in zip(st.columns(3), [f"{len(rows):02d}", f"{ready:02d}", "15 + 5"], ["Testigos confirmados", "Evidencias recibidas", "Minutos por expediente"]):
    with col:
        html(f'<div class="stat"><b>{value}</b><span>{label}</span></div>')
admin_mode = st.query_params.get("admin", "").lower() == "true"
tab_names = ["01 / Confirmar", "02 / Mi expediente", "03 / Cartelera", "04 / La noche", "05 / Investigaciones"]
if admin_mode:
    tab_names.append("⌑ Organizador")
if st.session_state.get("navigation") not in tab_names:
    st.session_state.navigation = tab_names[0]
tabs = st.tabs(tab_names, key="navigation", on_change="rerun")
registration, personal, board, info, investigation_tab = tabs[:5]
if registration.open:
    with registration:
        try:
            register_form()
        except storage.StorageError as exc:
            st.error(str(exc))
if personal.open:
    with personal:
        try:
            my_dossier()
        except storage.StorageError as exc:
            st.error(str(exc))
if board.open:
    with board:
        lineup(rows)
if info.open:
    with info:
        invitation()
if investigation_tab.open:
    with investigation_tab:
        try:
            investigations(admin_mode)
        except storage.StorageError as exc:
            st.error(str(exc))
if admin_mode and tabs[5].open:
    with tabs[5]:
        try:
            organizer(rows)
        except storage.StorageError as exc:
            st.error(str(exc))
html('<div class="footer">◈ &nbsp; PREPARA TUS PRUEBAS. LA VERDAD ESTÁ AHÍ FUERA. &nbsp; ◈</div>')
