"""Authorized, on-demand downloads: rendering a page never fetches file bytes."""
import streamlit as st
import storage


def download_document(filename, guest_id, *, label='Descargar mi archivo', key=None, email=None, token=None):
    # Capture cloud configuration on the Streamlit thread. Deferred callbacks run
    # elsewhere, where st.secrets/runtime context may not be available.
    remote = storage.remote_store()
    def load():
        if token is not None:
            guest = remote.lookup(email, token) if remote else storage.lookup(email, token)
            if not guest or guest['id'] != guest_id:
                raise ValueError('Tu sesión cambió. Vuelve a abrir el expediente.')
        file = remote.evidence(guest_id) if remote else storage.evidence(guest_id)
        if not file or file[0] != filename:
            raise ValueError('El documento cambió. Recarga el expediente antes de descargarlo.')
        return file[1]
    st.download_button(label, load, file_name=filename, mime=storage.content_type(filename),
                       key=key or f'guest_download_{guest_id}', on_click='ignore')
