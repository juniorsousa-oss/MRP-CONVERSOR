"""Pacote de conversores do MRP-CONVERSOR.

Também mantém a logo personalizada selecionada no Streamlit entre reruns e
novas sessões enquanto a instância do aplicativo permanecer ativa.
"""

import json
from pathlib import Path

import streamlit as st

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _BASE_DIR / "config"
_LOGO_BYTES = _CONFIG_DIR / "logo_usuario.bin"
_LOGO_META = _CONFIG_DIR / "logo_usuario.json"
_logo_memoria = {"bytes": None, "mime": None, "nome": None}


class _LogoPersistida:
    def __init__(self, dados: bytes, mime: str, nome: str):
        self._dados = dados
        self.type = mime or "image/png"
        self.name = nome or "logo_salva"

    def getvalue(self):
        return self._dados


def _salvar_logo(upload):
    dados = upload.getvalue()
    mime = getattr(upload, "type", None) or "image/png"
    nome = getattr(upload, "name", None) or "logo_salva"

    _logo_memoria.update({"bytes": dados, "mime": mime, "nome": nome})

    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _LOGO_BYTES.write_bytes(dados)
        _LOGO_META.write_text(
            json.dumps({"mime": mime, "nome": nome}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        # Mesmo que o filesystem não esteja disponível, a logo segue salva
        # em memória enquanto o processo do Streamlit permanecer ativo.
        pass


def _carregar_logo_persistida():
    if _logo_memoria["bytes"] is not None:
        return _LogoPersistida(
            _logo_memoria["bytes"],
            _logo_memoria["mime"],
            _logo_memoria["nome"],
        )

    try:
        if _LOGO_BYTES.exists() and _LOGO_META.exists():
            dados = _LOGO_BYTES.read_bytes()
            meta = json.loads(_LOGO_META.read_text(encoding="utf-8"))
            mime = meta.get("mime", "image/png")
            nome = meta.get("nome", "logo_salva")
            _logo_memoria.update({"bytes": dados, "mime": mime, "nome": nome})
            return _LogoPersistida(dados, mime, nome)
    except (OSError, json.JSONDecodeError):
        pass

    return None


_file_uploader_original = st.file_uploader


def _file_uploader_com_logo_persistente(*args, **kwargs):
    resultado = _file_uploader_original(*args, **kwargs)

    if kwargs.get("key") != "logo_empresa":
        return resultado

    if resultado is not None:
        _salvar_logo(resultado)
        return resultado

    return _carregar_logo_persistida()


if not getattr(st.file_uploader, "_mrp_logo_persistente", False):
    _file_uploader_com_logo_persistente._mrp_logo_persistente = True
    st.file_uploader = _file_uploader_com_logo_persistente
