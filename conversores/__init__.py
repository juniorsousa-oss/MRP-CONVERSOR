"""Pacote de conversores do MRP-CONVERSOR.

Mantém a logo personalizada selecionada no Streamlit entre reruns e novas
sessões enquanto a instância do aplicativo permanecer ativa e protege a
alteração da identidade visual com senha administrativa.
"""

import hmac
import json
import os
from collections.abc import Mapping
from pathlib import Path

import streamlit as st

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _BASE_DIR / "config"
_LOGO_BYTES = _CONFIG_DIR / "logo_usuario.bin"
_LOGO_META = _CONFIG_DIR / "logo_usuario.json"
_logo_memoria = {"bytes": None, "mime": None, "nome": None}
_WRAPPER_VERSION = "logo-auth-v2"


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
        # No Streamlit Cloud o filesystem pode ser efêmero. A logo continua
        # disponível em memória enquanto a instância permanecer ativa.
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


def _buscar_em_mapa(mapa, chaves):
    if not isinstance(mapa, Mapping):
        return ""
    for chave in chaves:
        try:
            valor = mapa.get(chave, "")
        except Exception:
            valor = ""
        if valor not in (None, ""):
            return str(valor)
    return ""


def _senha_logo_configurada() -> str:
    """Busca a senha nos Secrets sem expô-la no repositório."""
    chaves = (
        "LOGO_ADMIN_PASSWORD",
        "logo_admin_password",
        "SENHA_LOGO",
        "senha_logo",
    )

    try:
        senha = _buscar_em_mapa(st.secrets, chaves)
        if senha:
            return senha

        # Também aceita configurações organizadas em seções TOML, por exemplo:
        # [auth]\nLOGO_ADMIN_PASSWORD = "..."
        for secao in ("auth", "passwords", "admin", "logo"):
            try:
                bloco = st.secrets.get(secao, {})
            except Exception:
                bloco = {}
            senha = _buscar_em_mapa(bloco, chaves)
            if senha:
                return senha
    except Exception:
        pass

    for chave in chaves:
        senha = os.getenv(chave, "")
        if senha:
            return str(senha)

    return ""


def _alteracao_logo_autorizada() -> bool:
    senha_configurada = _senha_logo_configurada()

    if not senha_configurada:
        st.warning(
            "Alteração da logo bloqueada: não encontrei a senha nos Secrets. "
            "Use LOGO_ADMIN_PASSWORD = \"sua_senha\" e reinicie o app."
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

    st.caption("Alteração da logo protegida por senha.")
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


# Guarda a função original uma única vez. Isso evita encadear wrappers em
# reruns/reloads do Streamlit.
if not hasattr(st, "_mrp_file_uploader_original"):
    st._mrp_file_uploader_original = st.file_uploader

_file_uploader_original = st._mrp_file_uploader_original


def _file_uploader_com_logo_persistente(*args, **kwargs):
    if kwargs.get("key") != "logo_empresa":
        return _file_uploader_original(*args, **kwargs)

    logo_atual = _carregar_logo_persistida()

    # O seletor do tipo de relatório permanece livre. Apenas a troca da logo
    # passa pelo desbloqueio administrativo.
    if not _alteracao_logo_autorizada():
        return logo_atual

    kwargs["help"] = (
        "Selecione a nova logo da empresa. A alteração está liberada "
        "somente nesta sessão."
    )
    resultado = _file_uploader_original(*args, **kwargs)

    if resultado is not None:
        _salvar_logo(resultado)
        return resultado

    return logo_atual


_file_uploader_com_logo_persistente._mrp_logo_persistente = True
_file_uploader_com_logo_persistente._mrp_logo_wrapper_version = _WRAPPER_VERSION

# Aplicação deliberadamente incondicional: versões anteriores usavam uma flag
# genérica que podia manter o wrapper antigo carregado em memória após deploy.
st.file_uploader = _file_uploader_com_logo_persistente
