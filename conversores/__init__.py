"""Elementos visuais compartilhados do MRP-CONVERSOR."""

import streamlit as st


_original_header = st.sidebar.header
_logo_header_instalado = False


def _header_com_logo(texto, *args, **kwargs):
    """Exibe a caixa de logo imediatamente antes do cabeçalho Configuração."""
    global _logo_header_instalado

    if texto == "Configuração" and not _logo_header_instalado:
        try:
            st.sidebar.markdown(
                """
                <style>
                section[data-testid="stSidebar"] .logo-box-title {
                    font-size: 0.82rem;
                    font-weight: 600;
                    margin: 0 0 0.18rem 0;
                }
                section[data-testid="stSidebar"] .stFileUploader {
                    margin-top: 0;
                    margin-bottom: 0.35rem;
                }
                section[data-testid="stSidebar"] .stFileUploader section {
                    padding: 0.25rem 0.35rem;
                    min-height: 3.7rem;
                }
                section[data-testid="stSidebar"] .stFileUploader small {
                    font-size: 0.68rem;
                }
                </style>
                <div class="logo-box-title">Logo da empresa</div>
                """,
                unsafe_allow_html=True,
            )

            logo = st.sidebar.file_uploader(
                "Insira a logo da empresa",
                type=["png", "jpg", "jpeg"],
                key="logo_empresa",
                label_visibility="collapsed",
            )

            if logo is not None:
                st.sidebar.image(logo, width=145)

            _logo_header_instalado = True
        except Exception:
            pass

    return _original_header(texto, *args, **kwargs)


st.sidebar.header = _header_com_logo
