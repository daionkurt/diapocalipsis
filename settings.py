"""Server-only configuration, shared by Streamlit and maintenance scripts."""
import os
from pathlib import Path
import tomllib


def setting(name, default=""):
    if name in os.environ:
        return os.environ[name]
    import streamlit as st
    if st.runtime.exists():
        try:
            return st.secrets.get(name, default)
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            return default
    path = Path(__file__).parent / ".streamlit/secrets.toml"
    if not path.exists():
        return default
    return tomllib.loads(path.read_text()).get(name, default)
