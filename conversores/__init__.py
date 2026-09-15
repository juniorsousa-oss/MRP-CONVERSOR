"""Pacote de conversores do MRP-CONVERSOR.

Mantém a logo personalizada selecionada no Streamlit entre reruns e novas
sessões enquanto a instância do aplicativo permanecer ativa e protege a
alteração da identidade visual com senha administrativa.
"""

import hmac
import json
import os
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


def _senha_logo_configurada() -> str:
    """Busca a senha sem expô-la no repositório público."""
    senha = ""
    try:
        senha = st.secrets.get("LOGO_ADMIN_PASSWORD", "")
    except Exception:
        senha = ""

    if not senha:
        senha = os.getenv("LOGO_ADMIN_PASSWORD", "")

    return str(senha or "")


def _alteracao_logo_autorizada() -> bool:
    senha_configurada = _senha_logo_configurada()

    if not senha_configurada:
        st.warning(
            "Alteração da logo bloqueada: a senha administrativa ainda não foi configurada."
        )
        return False

    if st.session_state.get("_logo_admin_autorizado", False):
        st.success("Alteração da logo liberada nesta sessão.")
        if st.button(
            "Bloquear alteração da logo",
            key="_logo_admin_bloquear",
            use_container_width=True,
        ):
            st.session_state["_logo_admin_autorizado"] = False
            st.session_state.pop("_logo_admin_senha", None)
            st.rerun()
        return True

    senha_digitada = st.text_input(
        "Senha para alterar a logo",
        type="password",
        key="_logo_admin_senha",
        placeholder="Digite a senha administrativa",
    )

    if st.button(
        "Liberar alteração da logo",
        key="_logo_admin_liberar",
        use_container_width=True,
    ):
        if hmac.compare_digest(str(senha_digitada), senha_configurada):
            st.session_state["_logo_admin_autorizado"] = True
            st.session_state.pop("_logo_admin_senha", None)
            st.rerun()
        else:
            st.error("Senha incorreta.")

    return False


_file_uploader_original = st.file_uploader


def _file_uploader_com_logo_persistente(*args, **kwargs):
    if kwargs.get("key") != "logo_empresa":
        return _file_uploader_original(*args, **kwargs)

    logo_atual = _carregar_logo_persistida()

    # O seletor de relatório continua totalmente livre. Somente o uploader
    # responsável por trocar a logo exige autenticação.
    if not _alteracao_logo_autorizada():
        return logo_atual

    kwargs["help"] = "Selecione a nova logo da empresa. A alteração exige autorização administrativa."
    resultado = _file_uploader_original(*args, **kwargs)

    if resultado is not None:
        _salvar_logo(resultado)
        return resultado

    return logo_atual


if not getattr(st.file_uploader, "_mrp_logo_persistente", False):
    _file_uploader_com_logo_persistente._mrp_logo_persistente = True
    st.file_uploader = _file_uploader_com_logo_persistente
