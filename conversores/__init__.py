"""Inicialização visual do pacote de conversores."""

import base64
from pathlib import Path

import streamlit as st


_logo_path = Path(__file__).parent.parent / "config" / "logo_setta.svg"
_original_set_page_config = st.set_page_config
_logo_instalado = False


def _set_page_config_com_logo(*args, **kwargs):
    """Mantém a configuração original e insere o logo após a configuração da página."""
    global _logo_instalado
    resultado = _original_set_page_config(*args, **kwargs)
    if not _logo_instalado and _logo_path.exists():
        try:
            dados = base64.b64encode(_logo_path.read_bytes()).decode("ascii")
            st.sidebar.markdown(
                f'''<div style="display:flex;justify-content:center;align-items:center;padding:8px 0 18px 0;">
                    <img src="data:image/svg+xml;base64,{dados}" style="width:180px;max-width:100%;height:auto;display:block;" />
                </div>''',
                unsafe_allow_html=True,
            )
            _logo_instalado = True
        except OSError:
            pass
    return resultado


st.set_page_config = _set_page_config_com_logo
