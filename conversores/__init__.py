"""Pacote de conversores do MRP-CONVERSOR."""

# Ajuste visual da área da logo no sidebar.
# Mantém toda a lógica dos conversores intacta e apenas garante
# que o quadro que contém a logo tenha fundo branco.
import streamlit as st

_original_markdown = st.markdown


def _markdown_com_fundo_logo(body, *args, **kwargs):
    if isinstance(body, str) and ".logo-preview" in body and "background" not in body:
        body = body.replace(
            ".logo-preview {",
            ".logo-preview {\n            background: #ffffff;",
            1,
        )
    return _original_markdown(body, *args, **kwargs)


st.markdown = _markdown_com_fundo_logo
