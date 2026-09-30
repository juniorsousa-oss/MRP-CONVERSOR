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
    section[data-testid="stSidebar"] div[role="radiogroup"]{display:flex;flex-direction:column;gap:.34rem}
    section[data-testid="stSidebar"] div[role="radiogroup"] label{position:relative;width:100%;min-height:42px;display:flex!important;align-items:center!important;padding:.56rem .72rem .56rem .88rem!important;margin:0!important;border:1px solid transparent!important;border-radius:10px!important;background:transparent!important;cursor:pointer;box-sizing:border-box}
    section[data-testid="stSidebar"] div[role="radiogroup"] label>div:first-child{position:absolute!important;opacity:0!important;width:0!important;height:0!important;overflow:hidden!important}
    section[data-testid="stSidebar"] div[role="radiogroup"] label p{margin:0!important;font-size:.83rem!important;font-weight:600!important;color:#374151!important;line-height:1.2!important;text-transform:uppercase!important}
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover{background:#f8fafc!important;border-color:#e5e7eb!important}
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){background:#111827!important;border-color:#111827!important;box-shadow:0 5px 14px rgba(17,24,39,.14)!important}
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked)::before{content:"";position:absolute;left:.42rem;top:50%;width:4px;height:20px;border-radius:999px;background:#ef4444;transform:translateY(-50%)}
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p{color:#fff!important;font-weight:700!important}
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

    .section-band{margin:1.15rem 0 .85rem;padding:.78rem 1rem;background:#fff;border:1px solid #e5e8ee;border-left:5px solid #111827;border-radius:12px;box-shadow:0 3px 12px rgba(15,23,42,.035)}
    .section-kicker{font-size:.64rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#ef4444;margin-bottom:.14rem}
    .section-title{font-size:1.03rem;font-weight:900;color:#111827;letter-spacing:-.012em;text-transform:uppercase}

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
    .footer{text-align:center;color:#9298a1;font-size:.7rem;padding-top:1.4rem}

    @media(max-width:1000px){.source-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:900px){
      .block-container{padding-top:2rem!important;padding-left:1rem!important;padding-right:1rem!important;padding-bottom:2rem!important}
      .setta-logo-card{min-height:105px;margin-bottom:1.8rem;padding:.9rem 1rem}.setta-logo-card img{max-width:170px;max-height:72px}
      .app-title{font-size:2rem!important}.source-grid,.base-meta{grid-template-columns:1fr!important}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

logo_bytes, logo_mime = load_logo()

NAV_OPTIONS = {
    "RELATÓRIO GERAL": "Relatório Geral",
    "SALDO EM ESTOQUE": "Saldo em Estoque",
    "COMPRAS": "Compras — S.C + P.C + Pré-nota",
    "MRP — TC/TP": "MRP — TC/TP",
}

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

    selected_nav = st.radio(
        "NAVEGAÇÃO",
        list(NAV_OPTIONS.keys()),
        label_visibility="collapsed",
    )
    tipo_relatorio = NAV_OPTIONS[selected_nav]

    st.markdown("---")
    st.markdown(
        '<div class="sidebar-info-card">'
        '<b>CENTRAL DE DADOS</b><br>'
        'ATUALIZAÇÃO AUTOMÁTICA · 60 S'
        '</div>',
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
    '<p class="app-sub">Central de Dados • Conversão • Validação</p>',
    unsafe_allow_html=True,
)

cfg = pipelines.config_for(tipo_relatorio)

try:
    with st.spinner("Sincronizando com a Central de Dados..."):
        sync = pipelines.sync_pipeline(tipo_relatorio)
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
    '<div class="section-band">'
    '<div class="section-kicker">01 · FONTES</div>'
    '<div class="section-title">CENTRAL DE DADOS</div>'
    '</div>',
    unsafe_allow_html=True,
)

source_cards = []
for key in cfg["sources"]:
    meta = (sync.get("sources") or {}).get(key) or {}
    available = bool(meta.get("available"))
    accent = "#22c55e" if available else "#f59e0b"
    status_txt = "ATUALIZADO" if available else "AGUARDANDO"
    version = int(meta.get("version") or 0)
    source_cards.append(
        '<div class="source-card" '
        f'style="--accent:{accent}">'
        f'<div class="source-name">{pipelines.source_label(tipo_relatorio, key)}</div>'
        f'<div class="source-status">{status_txt}</div>'
        f'<div class="source-meta">v{version} • {fmt_dt(meta.get("last_update_at"))}</div>'
        '</div>'
    )

st.markdown(
    '<div class="source-grid">' + "".join(source_cards) + "</div>",
    unsafe_allow_html=True,
)

sync_status = str(sync.get("sync_status") or "")
if sync_status == "PROCESSADO":
    st.success(f"{cfg['derived_name']} atualizada automaticamente.")
elif sync_status == "ERRO":
    st.error(sync.get("error") or "Falha no processamento.")
elif sync_status == "AGUARDANDO":
    missing = [
        pipelines.source_label(tipo_relatorio, key)
        for key in cfg["sources"]
        if not bool(((sync.get("sources") or {}).get(key) or {}).get("available"))
    ]
    st.warning("Aguardando: " + " • ".join(missing))

result = sync.get("result")
current, derived_meta = pipelines.current_frame(tipo_relatorio)

if current is None and result and isinstance(result.get("tratado"), pd.DataFrame):
    current = result["tratado"]

st.markdown(
    '<div class="section-band">'
    '<div class="section-kicker">02 · RESULTADO</div>'
    f'<div class="section-title">{cfg["derived_name"]}</div>'
    '</div>',
    unsafe_allow_html=True,
)

if current is not None:
    processed_at = derived_meta.get("processed_at") or (sync.get("derived") or {}).get("processed_at")
    st.markdown(
        '<div class="base-card">'
        f'<div class="base-title">{cfg["derived_name"]}</div>'
        '<div class="base-meta">'
        '<div class="base-stat"><div class="base-label">Status</div><div class="base-value">ATUALIZADO</div></div>'
        f'<div class="base-stat"><div class="base-label">Registros</div><div class="base-value">{len(current):,}</div></div>'
        f'<div class="base-stat"><div class="base-label">Processado em</div><div class="base-value">{fmt_dt(processed_at)}</div></div>'
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
    }[tipo_relatorio]

    st.download_button(
        "EXPORTAR EXCEL",
        data=excel_bytes(current, cfg["derived_name"]),
        file_name=export_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
else:
    st.info("Base tratada ainda não disponível.")

with st.expander("CONTINGÊNCIA", expanded=False):
    b1, b2 = st.columns(2)
    if b1.button(
        "REPROCESSAR BASE",
        use_container_width=True,
        key=f"force_{cfg['derived_key']}",
    ):
        with st.spinner("Reprocessando..."):
            forced = pipelines.sync_pipeline(tipo_relatorio, force=True)
        if forced.get("sync_status") == "PROCESSADO":
            st.success("Base reprocessada.")
            st.rerun()
        else:
            st.error(forced.get("error") or "Não foi possível reprocessar.")

    if b2.button(
        "ATUALIZAR STATUS",
        use_container_width=True,
        key=f"refresh_{cfg['derived_key']}",
    ):
        st.rerun()

    source_options = {
        pipelines.source_label(tipo_relatorio, key): key
        for key in cfg["sources"]
    }
    selected_label = st.selectbox(
        "Fonte para alimentação emergencial",
        list(source_options.keys()),
        key=f"emergency_source_{cfg['derived_key']}",
    )
    selected_key = source_options[selected_label]

    upload = st.file_uploader(
        "Arquivo",
        type=["xlsx", "xls", "xlsm", "xltx", "csv"],
        key=f"emergency_upload_{selected_key}_{cfg['derived_key']}",
    )

    if upload is not None:
        raw = upload.getvalue()
        rows = pipelines.count_rows(upload.name, raw)
        c1, c2 = st.columns(2)
        c1.metric("Arquivo", upload.name)
        c2.metric("Registros", rows if rows else "—")

        if st.button(
            "ATUALIZAR FONTE NA CENTRAL",
            type="primary",
            use_container_width=True,
            key=f"emergency_save_{selected_key}_{cfg['derived_key']}",
        ):
            try:
                central.upload_source(
                    selected_key,
                    upload.name,
                    raw,
                    rows_count=rows,
                    mime_type=upload.type or "application/octet-stream",
                )
                st.success("Fonte atualizada.")
                st.rerun()
            except Exception as exc:
                st.error(f"Falha na atualização: {exc}")

st.markdown(
    '<div class="footer">SETTA · Conversor MRP integrado à Central de Dados</div>',
    unsafe_allow_html=True,
)
