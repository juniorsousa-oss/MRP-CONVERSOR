from __future__ import annotations

import base64
import io
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image
from streamlit_autorefresh import st_autorefresh

import central_data as central
import pipeline_sync as pipelines

ROOT = Path(__file__).parent
FAVICON = ROOT / "favicon.png.png"
CONFIG_LOGO = ROOT / "config" / "logo_setta.svg"

VISUAL_CONFIG = central.load_visual_config("setta_global")


def browser_icon():
    data = str(VISUAL_CONFIG.get("favicon_data") or "").strip()
    try:
        if data:
            raw = base64.b64decode(data, validate=True)
            image = Image.open(io.BytesIO(raw))
            image.load()
            return image
        if FAVICON.exists():
            return str(FAVICON)
    except Exception:
        pass
    return "📊"


st.set_page_config(
    page_title="CONVERSOR MRP | SETTA",
    page_icon=browser_icon(),
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_logo():
    data = str(VISUAL_CONFIG.get("logo_data") or "").strip()
    mime = str(VISUAL_CONFIG.get("logo_mime") or "image/png")
    if data:
        try:
            return base64.b64decode(data, validate=True), mime
        except Exception:
            pass
    try:
        return CONFIG_LOGO.read_bytes(), "image/svg+xml"
    except OSError:
        return None, None


def fmt_dt(value) -> str:
    if not value:
        return "—"
    try:
        stamp = pd.to_datetime(value, errors="coerce")
        if pd.isna(stamp):
            return "—"
        if getattr(stamp, "tzinfo", None) is not None:
            stamp = stamp.tz_convert("America/Sao_Paulo")
        return stamp.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "—"


def converter_general_status() -> dict:
    total = len(pipelines.PIPELINES)
    states = []
    errors = 0

    for report_type in pipelines.PIPELINES:
        try:
            states.append(pipelines.get_state(report_type))
        except Exception:
            errors += 1

    updated = 0
    processed_values = []
    stale = False
    waiting = False

    for state in states:
        derived = state.get("derived") or {}
        available = bool(derived.get("available"))
        ready = bool(state.get("ready"))
        is_stale = bool(state.get("stale"))
        stale = stale or is_stale
        waiting = waiting or (not ready) or (not available)

        if ready and available and not is_stale:
            updated += 1

        processed_at = derived.get("processed_at")
        if processed_at:
            try:
                stamp = pd.to_datetime(processed_at, errors="coerce", utc=True)
                if pd.notna(stamp):
                    processed_values.append(stamp)
            except Exception:
                pass

    if errors:
        status = "ERRO"
    elif waiting:
        status = "AGUARDANDO"
    elif stale:
        status = "ATUALIZAÇÃO PENDENTE"
    elif updated == total and total:
        status = "ATUALIZADO"
    else:
        status = "AGUARDANDO"

    last_update = max(processed_values).isoformat() if processed_values else None
    return {
        "status": status,
        "last_update": last_update,
        "summary": f"{updated}/{total} BASES OK",
    }


def converter_status_html(status_info: dict) -> str:
    status_info = status_info or {}
    status = str(status_info.get("status") or "AGUARDANDO").upper()
    when = fmt_dt(status_info.get("last_update"))
    summary = str(status_info.get("summary") or "").upper()
    meta = " · ".join(
        part for part in [when if when != "—" else "", summary] if part
    )
    if not meta:
        meta = "SEM ATUALIZAÇÃO REGISTRADA"

    return (
        '<div class="sidebar-status-card">'
        '<div class="sidebar-status-name">CONVERSOR MRP</div>'
        f'<div class="sidebar-status-value">{status}</div>'
        f'<div class="sidebar-status-meta">{meta}</div>'
        '</div>'
    )


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def excel_bytes(frame: pd.DataFrame, sheet_name: str) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    buffer.seek(0)
    return buffer.getvalue()


st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"]{background:#f4f7fb!important}
    [data-testid="stHeader"]{background:rgba(255,255,255,.96)!important}
    .block-container{max-width:1780px!important;padding-top:3.2rem!important;padding-left:2.7rem!important;padding-right:2.7rem!important;padding-bottom:3rem!important;width:100%!important}
    section[data-testid="stSidebar"]{background:#fff!important;border-right:1px solid #e8ebf0!important}
    section[data-testid="stSidebar"] .block-container{padding-top:1.6rem!important;padding-left:1rem!important;padding-right:1rem!important}
    .sidebar-brand{background:#f8fafc;border:1px solid #e5e8ee;border-radius:12px;padding:.9rem 1rem;margin:0 0 1.05rem 0}
    .sidebar-brand-title{font-size:.92rem;font-weight:800;color:#111827;letter-spacing:-.01em}
    .sidebar-brand-sub{margin-top:.18rem;font-size:.75rem;color:#6b7280}
    .sidebar-section-label{margin:.25rem 0 .45rem 0;color:#374151;font-size:.76rem;font-weight:800;text-transform:uppercase;letter-spacing:.055em}
    .sidebar-info-card{background:#f8fafc;border:1px solid #e5e8ee;border-radius:10px;padding:.75rem .85rem;color:#6b7280;font-size:.76rem;line-height:1.55}
    .sidebar-nav{display:flex;flex-direction:column;gap:.34rem;width:100%}
    .sidebar-nav-item{position:relative;width:100%;min-height:42px;display:flex;align-items:center;padding:.56rem .72rem .56rem calc(.88rem + 7px);margin:0;border:1px solid transparent;border-radius:10px;background:transparent;box-sizing:border-box;text-decoration:none!important;color:#374151!important;font-size:.83rem;font-weight:600;line-height:1.2;transition:background .14s ease,border-color .14s ease,box-shadow .14s ease,transform .14s ease}
    .sidebar-nav-item:hover{background:#f8fafc;border-color:#e5e7eb;transform:translateX(1px);color:#111827!important}
    .sidebar-nav-item.active{background:#111827!important;border-color:#111827!important;box-shadow:0 5px 14px rgba(17,24,39,.14)!important;color:#fff!important;font-weight:700}
    .sidebar-nav-item.active::before{content:"";position:absolute;left:.42rem;top:50%;width:4px;height:20px;border-radius:999px;background:#ef4444;transform:translateY(-50%)}
    .sidebar-status-spacer{height:.6rem!important;min-height:.6rem!important}
    .sidebar-status-card{background:#f8fafc;border:1px solid #e5e8ee;border-radius:10px;padding:.75rem .85rem;color:#6b7280;font-size:.72rem;line-height:1.5}
    .sidebar-status-name{font-size:.68rem;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.025em}
    .sidebar-status-value{margin-top:.16rem;font-size:.8rem;font-weight:900;color:#111827;text-transform:uppercase}
    .sidebar-status-meta{margin-top:.24rem;color:#6b7280;font-size:.66rem;line-height:1.45;text-transform:uppercase}
    section[data-testid="stSidebar"] hr{margin:.85rem 0!important}
    [data-testid="stAppViewContainer"] > .main,
    [data-testid="stAppViewContainer"] .main,
    [data-testid="stMain"],
    .stMain{width:100%!important;max-width:100%!important;margin-left:0!important;margin-right:0!important}
    [data-testid="stAppViewContainer"] .main .block-container,
    [data-testid="stMain"] .block-container,
    .stMain .block-container{width:100%!important;max-width:100%!important;margin-left:0!important;margin-right:0!important}
    section[data-testid="stSidebar"][aria-expanded="false"]{width:0!important;min-width:0!important;max-width:0!important;flex-basis:0!important}

    .setta-logo-card{width:100%;min-height:128px;display:flex;align-items:center;justify-content:center;background:#fff;border:1px solid #e5e8ee;border-radius:16px;box-shadow:0 4px 14px rgba(24,39,75,.08);box-sizing:border-box;margin:0 0 2.55rem 0;padding:1.1rem 2rem}
    .setta-logo-card img{display:block;width:auto;height:auto;max-width:205px;max-height:86px;object-fit:contain}
    .app-title{margin:0!important;padding:0!important;font-size:2.55rem!important;line-height:1.08!important;font-weight:800!important;letter-spacing:-.04em!important;color:#050505!important}
    .app-sub{margin-top:.72rem!important;margin-bottom:1.65rem!important;color:#4f5661!important;font-size:.94rem!important;line-height:1.35!important}

    .section-title{margin:0 0 1rem!important;color:#0f172a!important;font-size:1.28rem!important;font-weight:900!important;letter-spacing:-.02em;text-transform:uppercase}
    .section-band{margin:0 0 .95rem;padding:.82rem 1rem;background:#fff;border:1px solid #e5e8ee;border-left:5px solid #111827;border-radius:12px;box-shadow:0 3px 12px rgba(15,23,42,.035)}
    .section-band-kicker{font-size:.66rem;font-weight:900;letter-spacing:.085em;text-transform:uppercase;color:#ef4444;margin-bottom:.18rem}
    .section-band-title{font-size:1.08rem;font-weight:900;color:#111827;letter-spacing:-.015em;line-height:1.2;text-transform:uppercase}
    .section-band-note{margin-top:.22rem;color:#667085;font-size:.75rem;line-height:1.35}
    .topic-divider{height:1px;background:#cbd5e1;margin:1.55rem 0 1.05rem;width:100%}

    .source-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.72rem;margin:.25rem 0 1rem}
    .source-card{position:relative;background:#fff;border:1px solid #dfe3e8;border-radius:12px;padding:.82rem .9rem;box-shadow:0 3px 12px rgba(15,23,42,.035);overflow:hidden;min-height:96px}
    .source-card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent,#64748b)}
    .source-name{font-size:.69rem;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.035em}
    .source-status{margin-top:.26rem;font-size:.88rem;font-weight:900;color:#111827}
    .source-meta{margin-top:.28rem;font-size:.64rem;color:#94a3b8}

    .base-card{position:relative;background:#fff;border:1px solid #dfe3e8;border-radius:13px;padding:1rem 1.05rem;box-shadow:0 4px 14px rgba(15,23,42,.045);margin:.25rem 0 1rem}
    .base-title{font-size:.79rem;font-weight:900;color:#111827;text-transform:uppercase}
    .base-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.7rem;margin-top:.75rem}
    .base-stat{background:#f8fafc;border:1px solid #edf0f3;border-radius:9px;padding:.58rem .65rem}
    .base-label{font-size:.58rem;font-weight:900;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em}
    .base-value{margin-top:.18rem;font-size:.78rem;font-weight:900;color:#111827;overflow-wrap:anywhere}

    div[data-testid="stMetric"]{background:#fff;border:1px solid #e7eaf0;border-radius:12px;padding:.8rem 1rem}
    div[data-testid="stFileUploader"] section{border-radius:10px}
    div.stButton>button[kind="primary"],div.stDownloadButton>button{border-radius:9px;font-weight:700}
    [data-testid="stTabs"] button{font-weight:800!important;text-transform:uppercase!important;letter-spacing:.015em!important}
    div[data-testid="stMarkdownContainer"] h1,
    div[data-testid="stMarkdownContainer"] h2,
    div[data-testid="stMarkdownContainer"] h3,
    div[data-testid="stMarkdownContainer"] h4{text-transform:uppercase}
    [data-testid="stAlert"]{border-radius:12px!important;box-shadow:0 3px 12px rgba(15,23,42,.035)}
    .footer{text-align:center;color:#9298a1;font-size:.72rem;padding-top:1.2rem}

    @media(max-width:1000px){.source-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:900px){
      .block-container{padding-top:2rem!important;padding-left:1rem!important;padding-right:1rem!important;padding-bottom:2rem!important}
      .setta-logo-card{min-height:105px;margin-bottom:1.8rem;padding:.9rem 1rem}.setta-logo-card img{max-width:170px;max-height:72px}
      .app-title{font-size:2rem!important;line-height:1.12!important}.app-sub{font-size:.86rem!important;margin-bottom:1.35rem!important}.section-title{font-size:1.14rem!important}.source-grid,.base-meta{grid-template-columns:1fr!important}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

logo_bytes, logo_mime = load_logo()

NAV_OPTIONS = {
    "relatorio-geral": ("RELATÓRIO GERAL", "Relatório Geral"),
    "saldo-em-estoque": ("SALDO EM ESTOQUE", "Saldo em Estoque"),
    "compras": ("COMPRAS", "Compras — S.C + P.C + Pré-nota"),
    "mrp-tctp": ("MRP — TC/TP", "MRP — TC/TP"),
    "configuracoes": ("CONFIGURAÇÕES", None),
}


def current_nav_key() -> str:
    try:
        value = st.query_params.get("nav", "relatorio-geral")
    except Exception:
        value = "relatorio-geral"
    if isinstance(value, (list, tuple)):
        value = value[0] if value else "relatorio-geral"
    value = str(value or "relatorio-geral").strip()
    return value if value in NAV_OPTIONS else "relatorio-geral"


def sidebar_nav_html(active_key: str) -> str:
    items = []
    for key, (label, _) in NAV_OPTIONS.items():
        active = " active" if key == active_key else ""
        items.append(
            f'<a class="sidebar-nav-item{active}" href="?nav={key}" target="_self">'
            f'{label}'
            '</a>'
        )
    return '<div class="sidebar-nav">' + "".join(items) + "</div>"



with st.sidebar:
    st_autorefresh(
        interval=60_000,
        limit=None,
        key="mrp_conversor_central_refresh",
    )

    st.markdown(
        '<div class="sidebar-brand">'
        '<div class="sidebar-brand-title">CONVERSOR MRP</div>'
        '<div class="sidebar-brand-sub">Central de Dados SETTA</div>'
        '</div>'
        '<div class="sidebar-section-label">NAVEGAÇÃO</div>',
        unsafe_allow_html=True,
    )

    _nav_key = current_nav_key()
    selected_nav, tipo_relatorio = NAV_OPTIONS[_nav_key]
    st.markdown(
        sidebar_nav_html(_nav_key),
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown(
        '<div class="sidebar-info-card">'
        '<b>SISTEMA</b><br>'
        'ATUALIZAÇÃO AUTOMÁTICA · 60 S'
        '</div>',
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown(
        '<div class="sidebar-status-spacer"></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sidebar-section-label">STATUS GERAL</div>',
        unsafe_allow_html=True,
    )
    _converter_status_placeholder = st.empty()
    _converter_status_placeholder.markdown(
        converter_status_html(converter_general_status()),
        unsafe_allow_html=True,
    )


if logo_bytes:
    logo_b64 = base64.b64encode(logo_bytes).decode("ascii")
    logo_html = f'<img src="data:{logo_mime};base64,{logo_b64}" alt="SETTA">'
else:
    logo_html = '<div style="font-size:2rem;font-weight:800;color:#202124">SETTA</div>'

st.markdown(
    f'<div class="setta-logo-card">{logo_html}</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<h1 class="app-title">CONVERSOR MRP | SETTA</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="app-sub">CENTRAL DE DADOS • CONVERSÃO • VALIDAÇÃO</p>',
    unsafe_allow_html=True,
)

def section_band(kicker: str, title: str, note: str = "") -> None:
    note_html = (
        f'<div class="section-band-note">{note}</div>'
        if str(note or "").strip()
        else ""
    )
    st.markdown(
        f"""
        <div class="section-band">
            <div class="section-band-kicker">{kicker}</div>
            <div class="section-band-title">{title}</div>
            {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def source_cards_html(report_type: str, source_state: dict) -> str:
    cfg = pipelines.config_for(report_type)
    cards = []
    for key in cfg["sources"]:
        meta = (source_state or {}).get(key) or {}
        available = bool(meta.get("available"))
        accent = "#22c55e" if available else "#f59e0b"
        status_txt = "ATUALIZADO" if available else "AGUARDANDO"
        version = int(meta.get("version") or 0)
        cards.append(
            '<div class="source-card" '
            f'style="--accent:{accent}">'
            f'<div class="source-name">{pipelines.source_label(report_type, key)}</div>'
            f'<div class="source-status">{status_txt}</div>'
            f'<div class="source-meta">V{version} · {fmt_dt(meta.get("last_update_at"))}</div>'
            '</div>'
        )
    return '<div class="source-grid">' + "".join(cards) + "</div>"


def render_report(report_type: str) -> None:
    cfg = pipelines.config_for(report_type)

    try:
        with st.spinner("Sincronizando com a Central de Dados..."):
            sync = pipelines.sync_pipeline(report_type)
    except Exception as exc:
        sync = {
            "config": cfg,
            "sources": {},
            "derived": {},
            "versions": {},
            "ready": False,
            "stale": False,
            "sync_status": "ERRO",
            "result": None,
            "error": str(exc),
        }

    st.markdown(
        f'<div class="section-title">{selected_nav}</div>',
        unsafe_allow_html=True,
    )
    section_band("01 · RESULTADO", cfg["derived_name"])

    sync_status = str(sync.get("sync_status") or "")
    if sync_status == "ERRO":
        st.error(
            (sync.get("error") or "Falha no processamento.")
            + " Consulte CONFIGURAÇÕES > STATUS API."
        )
    elif sync_status == "AGUARDANDO":
        st.warning(
            "BASE AGUARDANDO ATUALIZAÇÃO. "
            "CONSULTE CONFIGURAÇÕES > STATUS API."
        )
    elif sync_status == "PROCESSADO":
        st.success(f'{cfg["derived_name"]} ATUALIZADA AUTOMATICAMENTE.')
        try:
            _converter_status_placeholder.markdown(
                converter_status_html(converter_general_status()),
                unsafe_allow_html=True,
            )
        except Exception:
            pass

    result = sync.get("result")
    derived_meta = sync.get("derived") or {}

    if result and isinstance(result.get("tratado"), pd.DataFrame):
        current = result["tratado"]
    else:
        current, downloaded_meta = pipelines.current_frame(
            report_type,
            derived_meta=derived_meta,
        )
        if downloaded_meta:
            derived_meta = downloaded_meta

    if current is not None:
        processed_at = (
            derived_meta.get("processed_at")
            or (sync.get("derived") or {}).get("processed_at")
        )
        st.markdown(
            '<div class="base-card">'
            f'<div class="base-title">{cfg["derived_name"]}</div>'
            '<div class="base-meta">'
            '<div class="base-stat"><div class="base-label">STATUS</div><div class="base-value">ATUALIZADO</div></div>'
            f'<div class="base-stat"><div class="base-label">REGISTROS</div><div class="base-value">{len(current):,}</div></div>'
            f'<div class="base-stat"><div class="base-label">PROCESSADO EM</div><div class="base-value">{fmt_dt(processed_at)}</div></div>'
            '</div></div>',
            unsafe_allow_html=True,
        )

        if result:
            errors = list(result.get("erros") or [])
            warnings = list(result.get("avisos") or [])
            if errors:
                with st.expander(f"ERROS ({len(errors)})", expanded=True):
                    for item in errors:
                        st.write(f"- {item}")
            if warnings:
                with st.expander(f"AVISOS ({len(warnings)})", expanded=False):
                    for item in warnings:
                        st.write(f"- {item}")

        st.dataframe(
            current.head(150),
            use_container_width=True,
            height=460,
            hide_index=True,
        )

        export_name = {
            "Relatório Geral": "RelatorioGeral_Tratado.xlsx",
            "Saldo em Estoque": "Estoque_Tratado.xlsx",
            "Compras — S.C + P.C + Pré-nota": "Compras_Tratado.xlsx",
            "MRP — TC/TP": "MRP_TC_TP_Tratado.xlsx",
        }[report_type]

        st.download_button(
            "EXPORTAR EXCEL",
            data=excel_bytes(current, cfg["derived_name"]),
            file_name=export_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    else:
        st.info(
            "BASE TRATADA AINDA NÃO DISPONÍVEL. "
            "CONSULTE CONFIGURAÇÕES > STATUS API."
        )


def render_status_api() -> None:
    tab_api, = st.tabs(["STATUS API"])

    with tab_api:
        for index, report_type in enumerate(pipelines.PIPELINES.keys(), start=1):
            if index > 1:
                st.markdown(
                    '<div class="topic-divider"></div>',
                    unsafe_allow_html=True,
                )

            cfg = pipelines.config_for(report_type)
            section_band(
                f"{index:02d} · {report_type.upper()}",
                "CENTRAL DE DADOS",
            )

            try:
                state = pipelines.get_state(report_type)
                st.markdown(
                    source_cards_html(report_type, state.get("sources") or {}),
                    unsafe_allow_html=True,
                )

                derived = state.get("derived") or {}
                if bool(derived.get("available")):
                    st.caption(
                        "BASE TRATADA · "
                        f'{cfg["derived_name"]} · '
                        f'{fmt_dt(derived.get("processed_at"))}'
                    )
                else:
                    st.caption(
                        f'BASE TRATADA · {cfg["derived_name"]} · AGUARDANDO'
                    )
            except Exception as exc:
                state = {"sources": {}, "derived": {}}
                st.error(f"Falha ao consultar a Central de Dados: {exc}")

            with st.expander(
                f"CONTINGÊNCIA · {report_type.upper()}",
                expanded=False,
            ):
                b1, b2 = st.columns(2)

                if b1.button(
                    "REPROCESSAR BASE",
                    use_container_width=True,
                    key=f'force_{cfg["derived_key"]}_status_api',
                ):
                    try:
                        with st.spinner("Reprocessando..."):
                            forced = pipelines.sync_pipeline(
                                report_type,
                                force=True,
                            )
                        if forced.get("sync_status") == "PROCESSADO":
                            pipelines.clear_current_frame_cache()
                            st.success("BASE REPROCESSADA.")
                            st.rerun()
                        else:
                            st.error(
                                forced.get("error")
                                or "NÃO FOI POSSÍVEL REPROCESSAR."
                            )
                    except Exception as exc:
                        st.error(f"FALHA NO REPROCESSAMENTO: {exc}")

                if b2.button(
                    "ATUALIZAR STATUS",
                    use_container_width=True,
                    key=f'refresh_{cfg["derived_key"]}_status_api',
                ):
                    st.rerun()

                source_options = {
                    pipelines.source_label(report_type, key): key
                    for key in cfg["sources"]
                }
                selected_label = st.selectbox(
                    "FONTE PARA ALIMENTAÇÃO EMERGENCIAL",
                    list(source_options.keys()),
                    key=f'emergency_source_{cfg["derived_key"]}_status_api',
                )
                selected_key = source_options[selected_label]

                upload = st.file_uploader(
                    "ARQUIVO",
                    type=["xlsx", "xls", "xlsm", "xltx", "csv"],
                    key=f'emergency_upload_{selected_key}_{cfg["derived_key"]}_status_api',
                )

                if upload is not None:
                    raw = upload.getvalue()
                    rows = pipelines.count_rows(upload.name, raw)
                    c1, c2 = st.columns(2)
                    c1.metric("ARQUIVO", upload.name)
                    c2.metric("REGISTROS", rows if rows else "—")

                    if st.button(
                        "ATUALIZAR FONTE NA CENTRAL",
                        type="primary",
                        use_container_width=True,
                        key=f'emergency_save_{selected_key}_{cfg["derived_key"]}_status_api',
                    ):
                        try:
                            central.upload_source(
                                selected_key,
                                upload.name,
                                raw,
                                rows_count=rows,
                                mime_type=(
                                    upload.type
                                    or "application/octet-stream"
                                ),
                            )
                            st.success("FONTE ATUALIZADA.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"FALHA NA ATUALIZAÇÃO: {exc}")


if selected_nav == "CONFIGURAÇÕES":
    render_status_api()
else:
    render_report(tipo_relatorio)


st.markdown(
    '<div class="footer">SETTA | Conversor MRP</div>',
    unsafe_allow_html=True,
)
