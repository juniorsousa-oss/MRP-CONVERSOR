"""Elementos visuais compartilhados do MRP-CONVERSOR."""

import streamlit as st

_original_set_page_config = st.set_page_config
_logo_instalado = False


def _set_page_config_com_logo(*args, **kwargs):
    """Configura a página e cria a caixa para inserir a logo da empresa."""
    global _logo_instalado
    resultado = _original_set_page_config(*args, **kwargs)

    if not _logo_instalado:
        try:
            st.sidebar.markdown(
                """
                <style>
                section[data-testid="stSidebar"] .stFileUploader {
                    margin-bottom: 0.25rem;
                }
                section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
                    margin-bottom: 0.15rem;
                }
                section[data-testid="stSidebar"] .stFileUploader section {
                    padding: 0.35rem 0.45rem;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            logo = st.sidebar.file_uploader(
                "Logo da empresa",
                type=["png", "jpg", "jpeg"],
                key="logo_empresa",
                help="Insira a logo da empresa. Ela será exibida no topo da barra lateral.",
            )

            if logo is not None:
                st.sidebar.image(logo, width=150)

            _logo_instalado = True
        except Exception:
            pass

    return resultado


st.set_page_config = _set_page_config_com_logo
