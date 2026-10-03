from __future__ import annotations

import base64
import io
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

import central_data as central
import pipeline_sync as pipelines

ROOT = Path(__file__).parent
FAVICON = ROOT / "favicon.png.png"
CONFIG_LOGO = ROOT / "config" / "logo_setta.svg"

VISUAL_CONFIG = central.load_visual_config("setta_global")

DEFAULT_SETTA_UI_CONFIG = {
    "header": {
        "enabled": True,
        "min_height": 150,
        "background": "#FFFFFF",
        "border_color": "#E5E8EE",
        "border_radius": 18,
        "padding_y": 18,
        "padding_x": 24,
        "logo_max_width": 220,
        "logo_max_height": 90,
        "margin_bottom": 24,
    },
    "top_actions": {
        "show_github": True,
        "show_more": True,
        "show_share": False,
        "show_favorite": False,
        "show_edit": False,
    },
    "theme": {
        "lock_light": True,
        "app_background": "#F4F7FB",
        "surface_background": "#FFFFFF",
        "text_color": "#111827",
    },
}


def _merge_config(base: dict, override: dict | None) -> dict:
    result = {}
    override = override if isinstance(override, dict) else {}
    for key, value in base.items():
        custom = override.get(key)
        if isinstance(value, dict):
            result[key] = _merge_config(
                value,
                custom if isinstance(custom, dict) else {},
            )
        else:
            result[key] = value if custom is None else custom
    for key, value in override.items():
        if key not in result:
            result[key] = value
    return result


SETTA_UI_CONFIG = _merge_config(
    DEFAULT_SETTA_UI_CONFIG,
    VISUAL_CONFIG.get("ui_config") or {},
)
HEADER_CONFIG = SETTA_UI_CONFIG["header"]
TOP_ACTIONS_CONFIG = SETTA_UI_CONFIG["top_actions"]
THEME_CONFIG = SETTA_UI_CONFIG["theme"]


def _int_cfg(value, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except Exception:
        return default


def _css_color(value, default: str) -> str:
    text = str(value or "").strip()
    if len(text) in {4, 7, 9} and text.startswith("#"):
        return text
    return default


def top_actions_css(config: dict) -> str:
    selectors = []
    if not bool(config.get("show_share", False)):
        selectors += [
            '[data-testid="stToolbar"] button[aria-label*="Share" i]',
            '[data-testid="stToolbar"] a[aria-label*="Share" i]',
            '[data-testid="stToolbar"] button[title*="Share" i]',
            '[data-testid="stToolbar"] a[title*="Share" i]',
            '[data-testid="stToolbar"] [data-testid*="share" i]',
        ]
    if not bool(config.get("show_favorite", False)):
        selectors += [
            '[data-testid="stToolbar"] button[aria-label*="Favorite" i]',
            '[data-testid="stToolbar"] a[aria-label*="Favorite" i]',
            '[data-testid="stToolbar"] button[title*="Favorite" i]',
            '[data-testid="stToolbar"] a[title*="Favorite" i]',
            '[data-testid="stToolbar"] button[aria-label*="Star" i]',
            '[data-testid="stToolbar"] a[aria-label*="Star" i]',
            '[data-testid="stToolbar"] [data-testid*="favorite" i]',
        ]
    if not bool(config.get("show_edit", False)):
        selectors += [
            '[data-testid="stToolbar"] button[aria-label*="Edit" i]',
            '[data-testid="stToolbar"] a[aria-label*="Edit" i]',
            '[data-testid="stToolbar"] button[title*="Edit" i]',
            '[data-testid="stToolbar"] a[title*="Edit" i]',
            '[data-testid="stToolbar"] [data-testid*="edit" i]',
        ]
    if not bool(config.get("show_github", True)):
        selectors += [
            '[data-testid="stToolbar"] a[href*="github.com"]',
            '[data-testid="stToolbar"] button[aria-label*="GitHub" i]',
            '[data-testid="stToolbar"] a[aria-label*="GitHub" i]',
        ]
    if not bool(config.get("show_more", True)):
        selectors += [
            '#MainMenu',
            '[data-testid="stToolbar"] button[aria-label*="menu" i]',
        ]
    if not selectors:
        return ""
    return ",\n".join(selectors) + "{display:none!important;}"


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


def converter_general_status(results: dict[str, dict] | None = None) -> dict:
    snapshot = results or st.session_state.get("_mrp_converter_boot_results") or {}
    total = len(pipelines.PIPELINES)
    errors = 0
    updated = 0
    processed_values = []
    stale = False
    waiting = False

    for report_type in pipelines.PIPELINES:
        state = snapshot.get(report_type) or {}
        sync_status = str(state.get("sync_status") or "").upper()
        derived = state.get("derived") or {}
        available = bool(derived.get("available"))
        ready = bool(state.get("ready"))
        is_stale = bool(state.get("stale"))

        if sync_status == "ERRO":
            errors += 1
        stale = stale or is_stale
        waiting = waiting or (not ready) or (not available)

        if ready and available and not is_stale and sync_status != "ERRO":
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
        "updated": updated,
        "total": total,
        "summary": f"{updated}/{total} BASES OK",
    }


def converter_status_html(status_info: dict) -> str:
    status_info = status_info or {}
    raw_status = str(status_info.get("status") or "AGUARDANDO").upper()
    when = fmt_dt(status_info.get("last_update"))
    updated = int(status_info.get("updated") or 0)
    total = int(status_info.get("total") or len(pipelines.PIPELINES))

    if raw_status == "ATUALIZADO":
        status_class = "status-ok"
        status_label = "ATUALIZADO"
    elif raw_status == "ERRO":
        status_class = "status-error"
        status_label = "ERRO"
    else:
        status_class = "status-warning"
        status_label = "ATENÇÃO"

    return (
        '<div class="sidebar-status-card">'
        '<div class="sidebar-status-name">CONVERSOR MRP</div>'
        f'<div class="sidebar-status-value {status_class}">{status_label}</div>'
        '<div class="sidebar-status-meta">'
        f'<div>ÚLTIMA ATUALIZAÇÃO: {when}</div>'
        f'<div>QNT DE BASES: {updated}/{total}</div>'
        '</div>'
        '</div>'
    )


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def excel_bytes(frame: pd.DataFrame, sheet_name: str) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    buffer.seek(0)
    return buffer.getvalue()


def ensure_all_bases_ready() -> dict[str, dict]:
    if st.session_state.get("_mrp_converter_boot_done"):
        return st.session_state.get("_mrp_converter_boot_results") or {}

    with st.spinner("ATUALIZANDO TODAS AS BASES DO CONVERSOR MRP..."):
        results = pipelines.sync_all_pipelines(force=False)
        pipelines.clear_current_frame_cache()
        warmed = pipelines.warm_all_current_frames(results)

    st.session_state["_mrp_converter_boot_results"] = results
    st.session_state["_mrp_converter_warmed_rows"] = warmed
    st.session_state["_mrp_converter_boot_done"] = True
    return results


_BOOT_RESULTS = ensure_all_bases_ready()


st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"]{background:#f4f7fb!important}
    [data-testid="stHeader"]{background:rgba(255,255,255,.96)!important}
    .block-container{max-width:1780px!important;padding-top:3.2rem!important;padding-left:2.7rem!important;padding-right:2.7rem!important;padding-bottom:3rem!important;width:100%!important}
    section[data-testid="stSidebar"]{background:#fff!important;border-right:1px solid #e8ebf0!important;width:260px!important;min-width:260px!important;max-width:260px!important;flex:0 0 260px!important;flex-basis:260px!important;overflow:hidden!important}
    section[data-testid="stSidebar"]>div{width:260px!important;min-width:260px!important;max-width:260px!important;box-sizing:border-box!important}
    /* PADRÃO SETTA · SIDEBAR 100% CONTROLADA POR HTML/CSS
       26 / 20 / 8 / 42 / 2 / 20 / 20 / 8 px */
    section[data-testid="stSidebar"] .block-container{
      width:260px!important;min-width:260px!important;max-width:260px!important;
      box-sizing:border-box!important;
      padding-top:26px!important;padding-left:16px!important;padding-right:16px!important;
    }
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{
      gap:0!important;row-gap:0!important;
    }
    section[data-testid="stSidebar"] div[data-testid="stElementContainer"]:has(.setta-sidebar){
      margin:0!important;padding:0!important;
    }
    .setta-sidebar{
      width:100%!important;
      margin:0!important;
      padding:0!important;
      box-sizing:border-box!important;
      font-family:inherit!important;
    }
    .setta-sidebar *{box-sizing:border-box!important}

    .sidebar-brand{
      width:100%!important;
      background:#f8fafc!important;
      border:1px solid #e5e8ee!important;
      border-radius:12px!important;
      padding:14px 16px!important;
      margin:0 0 20px 0!important;
    }
    .sidebar-brand-title{
      margin:0!important;padding:0!important;
      font-size:15px!important;font-weight:800!important;line-height:18px!important;
      color:#111827!important;letter-spacing:-.01em!important;
    }
    .sidebar-brand-sub{
      margin:3px 0 0 0!important;padding:0!important;
      font-size:12px!important;font-weight:400!important;line-height:16px!important;
      color:#6b7280!important;
    }

    .sidebar-section-label{
      display:block!important;
      margin:0 0 8px 0!important;padding:0!important;
      color:#374151!important;
      font-size:12px!important;line-height:15px!important;font-weight:800!important;
      text-transform:uppercase!important;letter-spacing:.055em!important;
    }

    .sidebar-nav{
      display:flex!important;
      flex-direction:column!important;
      width:100%!important;
      gap:2px!important;
      margin:0!important;padding:0!important;
    }
    .sidebar-nav-link{
      position:relative!important;
      display:flex!important;
      align-items:center!important;
      justify-content:flex-start!important;
      width:100%!important;
      height:42px!important;min-height:42px!important;max-height:42px!important;
      margin:0!important;
      padding:0 12px 0 24px!important;
      border:1px solid transparent!important;
      border-radius:10px!important;
      background:transparent!important;
      color:#374151!important;
      text-decoration:none!important;
      font-size:13px!important;line-height:16px!important;font-weight:500!important;
      text-align:left!important;
    }
    .sidebar-nav-link:hover{
      background:#f8fafc!important;
      border-color:#e5e7eb!important;
      color:#111827!important;
      text-decoration:none!important;
    }
    .sidebar-nav-link.active{
      background:#111827!important;
      border-color:#111827!important;
      color:#ffffff!important;
      font-weight:700!important;
      box-shadow:0 5px 14px rgba(17,24,39,.14)!important;
    }
    .sidebar-nav-link.active::before{
      content:""!important;
      position:absolute!important;
      left:7px!important;top:50%!important;
      width:4px!important;height:20px!important;
      border-radius:999px!important;
      background:#ef4444!important;
      transform:translateY(-50%)!important;
    }

    /* SETTA UI — Sidebar Operacional V1 · navegação nativa */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{
      gap:0!important;row-gap:0!important;
    }
    section[data-testid="stSidebar"] div[data-testid="stElementContainer"]:has(.sidebar-section-label){
      margin:0!important;padding:0!important;
    }
    section[data-testid="stSidebar"] [class*="st-key-setta_nav_"]{
      margin:0 0 2px 0!important;
      padding:0!important;
    }
    section[data-testid="stSidebar"] .st-key-setta_nav_0{
      margin-top:8px!important;
    }
    section[data-testid="stSidebar"] [class*="st-key-setta_nav_"] button{
      position:relative!important;
      width:100%!important;
      min-height:42px!important;height:42px!important;max-height:42px!important;
      margin:0!important;
      padding:0 12px 0 24px!important;
      border-radius:10px!important;
      justify-content:flex-start!important;
      text-align:left!important;
      box-shadow:none!important;
    }
    section[data-testid="stSidebar"] [class*="st-key-setta_nav_"] button > div{
      width:100%!important;
      justify-content:flex-start!important;
      text-align:left!important;
    }
    section[data-testid="stSidebar"] [class*="st-key-setta_nav_"] button p{
      width:100%!important;
      margin:0!important;
      padding:0!important;
      text-align:left!important;
      font-size:13px!important;
      line-height:16px!important;
    }
    section[data-testid="stSidebar"] [class*="st-key-setta_nav_"] button[data-testid="stBaseButton-secondary"]{
      background:transparent!important;
      border:1px solid transparent!important;
      color:#374151!important;
      font-weight:500!important;
    }
    section[data-testid="stSidebar"] [class*="st-key-setta_nav_"] button[data-testid="stBaseButton-secondary"]:hover{
      background:#f8fafc!important;
      border-color:#e5e7eb!important;
      color:#111827!important;
    }
    section[data-testid="stSidebar"] [class*="st-key-setta_nav_"] button[data-testid="stBaseButton-primary"]{
      background:#111827!important;
      border:1px solid #111827!important;
      color:#fff!important;
      font-weight:700!important;
      box-shadow:0 5px 14px rgba(17,24,39,.14)!important;
    }
    section[data-testid="stSidebar"] [class*="st-key-setta_nav_"] button[data-testid="stBaseButton-primary"]::before{
      content:""!important;
      position:absolute!important;
      left:7px!important;top:50%!important;
      width:4px!important;height:20px!important;
      border-radius:999px!important;
      background:#ef4444!important;
      transform:translateY(-50%)!important;
    }

    .sidebar-divider{
      display:block!important;
      width:100%!important;
      height:1px!important;min-height:1px!important;
      background:#d1d5db!important;
      margin:18px 0 20px 0!important;
      padding:0!important;
    }

    .sidebar-status-card{
      width:100%!important;
      background:#f8fafc!important;
      border:1px solid #e5e8ee!important;
      border-radius:10px!important;
      padding:12px 14px!important;
      margin:0!important;
      color:#6b7280!important;
    }
    .sidebar-status-name{
      margin:0!important;padding:0!important;
      font-size:11px!important;line-height:14px!important;font-weight:800!important;
      color:#64748b!important;text-transform:uppercase!important;letter-spacing:.025em!important;
    }
    .sidebar-status-value{
      margin:4px 0 0 0!important;padding:0!important;
      font-size:13px!important;line-height:16px!important;font-weight:900!important;
      text-transform:uppercase!important;
    }
    .sidebar-status-value.status-ok{color:#16a34a!important}
    .sidebar-status-value.status-warning{color:#f59e0b!important}
    .sidebar-status-value.status-error{color:#ef4444!important}
    .sidebar-status-meta{
      margin:6px 0 0 0!important;padding:0!important;
      color:#6b7280!important;
      font-size:11px!important;line-height:15px!important;
      text-transform:uppercase!important;
    }
    [data-testid="stAppViewContainer"] > .main,
    [data-testid="stAppViewContainer"] .main,
    [data-testid="stMain"],
    .stMain{width:100%!important;max-width:100%!important;margin-left:0!important;margin-right:0!important}
    [data-testid="stAppViewContainer"] .main .block-container,
    [data-testid="stMain"] .block-container,
    .stMain .block-container{width:100%!important;max-width:100%!important;margin-left:0!important;margin-right:0!important}
    section[data-testid="stSidebar"][aria-expanded="false"]{width:0!important;min-width:0!important;max-width:0!important;flex:0 0 0!important;flex-basis:0!important}
    section[data-testid="stSidebar"][aria-expanded="false"]>div{width:0!important;min-width:0!important;max-width:0!important}

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

_header_height = _int_cfg(
    HEADER_CONFIG.get("min_height"), 150, 90, 320
)
_header_radius = _int_cfg(
    HEADER_CONFIG.get("border_radius"), 18, 0, 40
)
_header_padding_y = _int_cfg(
    HEADER_CONFIG.get("padding_y"), 18, 0, 80
)
_header_padding_x = _int_cfg(
    HEADER_CONFIG.get("padding_x"), 24, 0, 120
)
_logo_max_width = _int_cfg(
    HEADER_CONFIG.get("logo_max_width"), 220, 80, 600
)
_logo_max_height = _int_cfg(
    HEADER_CONFIG.get("logo_max_height"), 90, 40, 240
)
_header_margin_bottom = _int_cfg(
    HEADER_CONFIG.get("margin_bottom"), 24, 0, 100
)
_header_background = _css_color(
    HEADER_CONFIG.get("background"), "#FFFFFF"
)
_header_border = _css_color(
    HEADER_CONFIG.get("border_color"), "#E5E8EE"
)
_app_background = _css_color(
    THEME_CONFIG.get("app_background"), "#F4F7FB"
)
_surface_background = _css_color(
    THEME_CONFIG.get("surface_background"), "#FFFFFF"
)
_text_color = _css_color(
    THEME_CONFIG.get("text_color"), "#111827"
)
_toolbar_rules = top_actions_css(TOP_ACTIONS_CONFIG)
_light_lock_css = ""
if bool(THEME_CONFIG.get("lock_light", True)):
    _light_lock_css = f"""
    :root, html, body, .stApp{{
      color-scheme:light!important;
    }}
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"]{{
      background:{_app_background}!important;
      color:{_text_color}!important;
    }}
    section[data-testid="stSidebar"],
    [data-testid="stHeader"]{{
      background:{_surface_background}!important;
      color:{_text_color}!important;
    }}
    input, textarea,
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"]{{
      color-scheme:light!important;
    }}
    """

st.markdown(
    f"""
    <style>
    /* SETTA UI — Header Superior V1 */
    .setta-logo-card{{
      min-height:{_header_height}px!important;
      background:{_header_background}!important;
      border-color:{_header_border}!important;
      border-radius:{_header_radius}px!important;
      padding:{_header_padding_y}px {_header_padding_x}px!important;
      margin-bottom:{_header_margin_bottom}px!important;
    }}
    .setta-logo-card img{{
      max-width:{_logo_max_width}px!important;
      max-height:{_logo_max_height}px!important;
    }}
    /* SETTA UI — Top Actions V1 */
    {_toolbar_rules}
    /* SETTA UI — Light Lock V1 */
    {_light_lock_css}
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
    key = str(st.session_state.get("_mrp_conversor_nav") or "relatorio-geral")
    if key not in NAV_OPTIONS:
        key = "relatorio-geral"
        st.session_state["_mrp_conversor_nav"] = key
    return key


def set_nav_key(key: str) -> None:
    if key in NAV_OPTIONS:
        st.session_state["_mrp_conversor_nav"] = key


with st.sidebar:
    _nav_key = current_nav_key()
    selected_nav, tipo_relatorio = NAV_OPTIONS[_nav_key]

    st.markdown(
        '<div class="sidebar-brand">'
        '<div class="sidebar-brand-title">CONVERSOR MRP</div>'
        '<div class="sidebar-brand-sub">Central de Dados SETTA</div>'
        '</div>'
        '<div class="sidebar-section-label">NAVEGAÇÃO</div>',
        unsafe_allow_html=True,
    )

    for _nav_index, (_key, (_label, _report_type)) in enumerate(NAV_OPTIONS.items()):
        st.button(
            _label,
            key=f"setta_nav_{_nav_index}",
            type="primary" if _key == _nav_key else "secondary",
            use_container_width=True,
            on_click=set_nav_key,
            args=(_key,),
        )

    _status_html = converter_status_html(
        converter_general_status(_BOOT_RESULTS)
    )
    st.markdown(
        '<div class="sidebar-divider"></div>'
        '<div class="sidebar-section-label">STATUS GERAL</div>'
        f'{_status_html}',
        unsafe_allow_html=True,
    )


if logo_bytes:
    logo_b64 = base64.b64encode(logo_bytes).decode("ascii")
    logo_html = f'<img src="data:{logo_mime};base64,{logo_b64}" alt="SETTA">'
else:
    logo_html = '<div style="font-size:2rem;font-weight:800;color:#202124">SETTA</div>'

if bool(HEADER_CONFIG.get("enabled", True)):
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

    boot_meta = (_BOOT_RESULTS or {}).get(report_type) or {}
    sync = {
        "config": cfg,
        "sources": boot_meta.get("sources") or {},
        "derived": boot_meta.get("derived") or {},
        "versions": boot_meta.get("versions") or {},
        "ready": bool(boot_meta.get("ready")),
        "stale": bool(boot_meta.get("stale")),
        "sync_status": (
            boot_meta.get("sync_status")
            or (
                "ATUALIZADO"
                if boot_meta.get("ready") and not boot_meta.get("stale")
                else "AGUARDANDO"
            )
        ),
        "result": None,
        "error": boot_meta.get("error") or "",
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
    elif sync_status == "ATUALIZADO":
        st.caption(f'{cfg["derived_name"]} JÁ ESTÁ ATUALIZADA.')

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
    tab_api, tab_layout = st.tabs(["STATUS API", "LAYOUT SETTA"])

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
                            st.session_state["_mrp_converter_boot_results"] = pipelines.inspect_all_pipelines()
                            st.session_state["_mrp_converter_boot_done"] = True
                            st.success("BASE REPROCESSADA.")
                            st.rerun()
                        else:
                            _force_error = str(forced.get("error") or "")
                            if "aguardando normalização" in _force_error.lower():
                                st.warning(_force_error)
                            else:
                                st.error(
                                    _force_error
                                    or "NÃO FOI POSSÍVEL REPROCESSAR."
                                )
                    except Exception as exc:
                        st.error(f"FALHA NO REPROCESSAMENTO: {exc}")

                if b2.button(
                    "ATUALIZAR STATUS",
                    use_container_width=True,
                    key=f'refresh_{cfg["derived_key"]}_status_api',
                ):
                    st.session_state["_mrp_converter_boot_results"] = pipelines.inspect_all_pipelines()
                    st.session_state["_mrp_converter_boot_done"] = True
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
                    size_mb = len(raw) / (1024 * 1024)
                    c1, c2 = st.columns(2)
                    c1.metric("ARQUIVO", upload.name)
                    c2.metric("TAMANHO", f"{size_mb:.2f} MB")

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
                                rows_count=0,
                                mime_type=(
                                    upload.type
                                    or "application/octet-stream"
                                ),
                            )
                            st.session_state["_mrp_converter_boot_results"] = pipelines.inspect_all_pipelines()
                            st.session_state["_mrp_converter_boot_done"] = True
                            st.session_state["_mrp_normalization_pending"] = selected_key
                            st.success(
                                "FONTE BRUTA ATUALIZADA. A CENTRAL DE DADOS IRÁ "
                                "NORMALIZAR O ARQUIVO E O PIPELINE SERÁ PROCESSADO "
                                "AUTOMATICAMENTE."
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(f"FALHA NA ATUALIZAÇÃO: {exc}")

    with tab_layout:
        section_band(
            "LAYOUT · SETTA",
            "HEADER SUPERIOR, AÇÕES E TEMA",
            "Configuração visual compartilhada pelo padrão SETTA.",
        )

        with st.form("setta_layout_config_form", border=False):
            st.markdown("**BALÃO SUPERIOR**")
            h1, h2, h3 = st.columns(3)
            header_enabled = h1.checkbox(
                "EXIBIR BALÃO",
                value=bool(HEADER_CONFIG.get("enabled", True)),
            )
            header_height = h2.number_input(
                "ALTURA MÍNIMA (PX)",
                min_value=90,
                max_value=320,
                value=_int_cfg(
                    HEADER_CONFIG.get("min_height"), 150, 90, 320
                ),
                step=5,
            )
            header_radius = h3.number_input(
                "RAIO (PX)",
                min_value=0,
                max_value=40,
                value=_int_cfg(
                    HEADER_CONFIG.get("border_radius"), 18, 0, 40
                ),
                step=1,
            )

            h4, h5, h6 = st.columns(3)
            logo_width = h4.number_input(
                "LOGO · LARGURA MÁX. (PX)",
                min_value=80,
                max_value=600,
                value=_int_cfg(
                    HEADER_CONFIG.get("logo_max_width"), 220, 80, 600
                ),
                step=5,
            )
            logo_height = h5.number_input(
                "LOGO · ALTURA MÁX. (PX)",
                min_value=40,
                max_value=240,
                value=_int_cfg(
                    HEADER_CONFIG.get("logo_max_height"), 90, 40, 240
                ),
                step=5,
            )
            margin_bottom = h6.number_input(
                "ESPAÇO INFERIOR (PX)",
                min_value=0,
                max_value=100,
                value=_int_cfg(
                    HEADER_CONFIG.get("margin_bottom"), 24, 0, 100
                ),
                step=2,
            )

            st.markdown("**BOTÕES SUPERIORES**")
            a1, a2, a3, a4, a5 = st.columns(5)
            show_github = a1.checkbox(
                "GITHUB",
                value=bool(TOP_ACTIONS_CONFIG.get("show_github", True)),
            )
            show_more = a2.checkbox(
                "3 PONTOS",
                value=bool(TOP_ACTIONS_CONFIG.get("show_more", True)),
            )
            show_share = a3.checkbox(
                "SHARE",
                value=bool(TOP_ACTIONS_CONFIG.get("show_share", False)),
            )
            show_favorite = a4.checkbox(
                "FAVORITO",
                value=bool(TOP_ACTIONS_CONFIG.get("show_favorite", False)),
            )
            show_edit = a5.checkbox(
                "EDITAR",
                value=bool(TOP_ACTIONS_CONFIG.get("show_edit", False)),
            )

            st.markdown("**TEMA**")
            lock_light = st.checkbox(
                "TRAVAR A INTERFACE NO TEMA LIGHT",
                value=bool(THEME_CONFIG.get("lock_light", True)),
            )

            save_layout = st.form_submit_button(
                "SALVAR PADRÃO VISUAL",
                type="primary",
                use_container_width=True,
            )

        if save_layout:
            updated_ui_config = {
                **SETTA_UI_CONFIG,
                "header": {
                    **HEADER_CONFIG,
                    "enabled": bool(header_enabled),
                    "min_height": int(header_height),
                    "border_radius": int(header_radius),
                    "logo_max_width": int(logo_width),
                    "logo_max_height": int(logo_height),
                    "margin_bottom": int(margin_bottom),
                },
                "top_actions": {
                    "show_github": bool(show_github),
                    "show_more": bool(show_more),
                    "show_share": bool(show_share),
                    "show_favorite": bool(show_favorite),
                    "show_edit": bool(show_edit),
                },
                "theme": {
                    **THEME_CONFIG,
                    "lock_light": bool(lock_light),
                },
            }
            try:
                central.save_visual_config(
                    app_key="setta_global",
                    logo_data=str(VISUAL_CONFIG.get("logo_data") or ""),
                    logo_mime=str(
                        VISUAL_CONFIG.get("logo_mime") or "image/png"
                    ),
                    favicon_data=str(
                        VISUAL_CONFIG.get("favicon_data") or ""
                    ),
                    favicon_mime=str(
                        VISUAL_CONFIG.get("favicon_mime") or "image/png"
                    ),
                    ui_config=updated_ui_config,
                )
                central.load_visual_config.clear()
                st.success("PADRÃO VISUAL SETTA ATUALIZADO.")
                st.rerun()
            except Exception as exc:
                st.error(f"FALHA AO SALVAR O LAYOUT: {exc}")


if selected_nav == "CONFIGURAÇÕES":
    render_status_api()
else:
    render_report(tipo_relatorio)


st.markdown(
    '<div class="footer">SETTA | Conversor MRP</div>',
    unsafe_allow_html=True,
)
