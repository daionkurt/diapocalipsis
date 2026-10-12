"""Private document downloads; file contents are never rendered in the app."""
import streamlit as st
from storage import content_type


def show_document(filename, contents, guest_id):
    st.download_button('Descargar mi archivo', contents, file_name=filename,
                       mime=content_type(filename), key=f'guest_download_{guest_id}')
