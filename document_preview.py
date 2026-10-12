"""Private document previews: local rendering only, no third-party document service."""
from io import BytesIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

import streamlit as st
from storage import content_type

MAX_PREVIEW_ENTRY = 4 * 1024 * 1024


def text_contents(contents):
    encoding = 'utf-16' if contents.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    try:
        return contents.decode(encoding)
    except UnicodeDecodeError:
        return contents.decode('cp1252', errors='replace')


def read_entry(archive, name):
    if archive.getinfo(name).file_size > MAX_PREVIEW_ENTRY:
        raise ValueError('El contenido es demasiado grande para la vista previa. Puedes descargar el documento completo.')
    return archive.read(name)


def office_text(filename, contents):
    """Extract document paragraphs or ordered slide text without executing embedded content."""
    with zipfile.ZipFile(BytesIO(contents)) as archive:
        if filename.lower().endswith('.docx'):
            root = ET.fromstring(read_entry(archive, 'word/document.xml'))
            ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            lines = [''.join(t.text or '' for t in p.iter(ns + 't')) for p in root.iter(ns + 'p')]
            return [('Documento', '\n'.join(lines))]
        slides = sorted((name for name in archive.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', name)), key=lambda name: int(re.search(r'slide(\d+)', name).group(1)))
        sections = []
        for name in slides[:100]:
            root = ET.fromstring(read_entry(archive, name))
            ns = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
            lines = [''.join(t.text or '' for t in p.iter(ns + 't')) for p in root.iter(ns + 'p')]
            number = re.search(r'slide(\d+)', name).group(1)
            sections.append((f'Diapositiva {number}', '\n'.join(lines)))
        return sections


def show_document(filename, contents, guest_id):
    st.subheader('Tu documento')
    st.download_button('Descargar mi archivo', contents, file_name=filename, mime=content_type(filename), key=f'guest_download_{guest_id}')
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == '.pdf':
            st.pdf(contents, height=650, key=f'guest_pdf_{guest_id}')
        elif suffix == '.txt':
            st.code(text_contents(contents), language=None, wrap_lines=True)
        elif suffix in {'.docx', '.pptx'}:
            st.caption('Vista del texto. Descarga el archivo para ver el diseño, las imágenes y las animaciones originales.')
            sections = office_text(filename, contents)
            for title, text in sections:
                with st.expander(title, expanded=True):
                    st.text(text or 'Este documento no contiene texto visible en esta sección.')
            if suffix == '.pptx' and len(sections) == 100:
                st.caption('Se muestran las primeras 100 diapositivas.')
        elif suffix == '.key':
            with zipfile.ZipFile(BytesIO(contents)) as archive:
                names = archive.namelist()
                if 'QuickLook/Preview.pdf' in names:
                    st.pdf(read_entry(archive, 'QuickLook/Preview.pdf'), height=650, key=f'guest_key_pdf_{guest_id}')
                else:
                    preview = next((name for name in ('preview.jpg', 'QuickLook/Thumbnail.jpg', 'QuickLook/Thumbnail.png') if name in names), None)
                    if preview:
                        st.image(read_entry(archive, preview), caption='Vista previa incluida en tu Keynote')
                    st.info('Descarga el archivo para abrir la presentación completa en Keynote.')
        else:
            st.info('Descarga el archivo para abrirlo en Word.')
    except (ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
        st.info('No pudimos mostrar la vista previa de este documento. Puedes descargar el archivo original.')
