"""Inicialização visual do pacote de conversores."""

from pathlib import Path

import streamlit as st


_logo_path = Path(__file__).parent.parent / "config" / "logo_setta.svg"
_original_set_page_config = st.set_page_config
_logo_instalado = False


def _set_page_config_com_logo(*args, **kwargs):
    """Mantém a configuração original e insere o logo no topo da barra lateral."""
    global _logo_instalado
    resultado = _original_set_page_config(*args, **kwargs)
    if not _logo_instalado and _logo_path.exists():
        try:
            st.sidebar.image(str(_logo_path), width=180)
            _logo_instalado = True
        except Exception:
            pass
    return resultado


st.set_page_config = _set_page_config_com_logo
