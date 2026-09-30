from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

import central_data as central
from conversores.compras import processar_compras
from conversores.estoque import processar_estoque
from conversores.relatorio_geral import processar_relatorio_geral
from conversores.tc_tp import processar_tc_tp

ROOT = Path(__file__).parent
CONFIG_ENDERECOS = ROOT / "config" / "enderecos_nao_disponiveis.json"

PIPELINES = {
    "Relatório Geral": {
        "pipeline_key": "relatorio_geral_tratado",
        "derived_key": "relatorio_geral_tratado",
        "derived_name": "RELATÓRIO GERAL TRATADO",
        "sources": ["relatorio_geral", "for001", "for022"],
        "labels": {
            "relatorio_geral": "RELATÓRIO GERAL",
            "for001": "FOR001",
            "for022": "FOR022",
        },
    },
    "Saldo em Estoque": {
        "pipeline_key": "estoque_tratado",
        "derived_key": "estoque_tratado",
        "derived_name": "ESTOQUE TRATADO",
        "sources": ["analitico", "endereco"],
        "labels": {
            "analitico": "ANALÍTICO",
            "endereco": "ENDEREÇO",
        },
    },
    "Compras — S.C + P.C + Pré-nota": {
        "pipeline_key": "compras_tratado",
        "derived_key": "compras_tratado",
        "derived_name": "COMPRAS TRATADO",
        "sources": ["sc", "pc", "pre_nota"],
        "labels": {
            "sc": "S.C",
            "pc": "P.C",
            "pre_nota": "PRÉ NOTA",
        },
    },
    "MRP — TC/TP": {
        "pipeline_key": "tctp_tratado",
        "derived_key": "tctp_tratado",
        "derived_name": "TCTP TRATADO",
        "sources": ["pmp", "h001"],
        "labels": {
            "pmp": "PMP",
            "h001": "H001",
        },
    },
}


def read_excel_safe(file_obj, **kwargs):
    try:
        return pd.read_excel(file_obj, **kwargs)
    except TypeError as exc:
        if "MultiCellRange" not in str(exc):
            raise
        try:
            file_obj.seek(0)
        except Exception:
            pass
        return pd.read_excel(file_obj, engine="calamine", **kwargs)


def _load_unavailable_addresses() -> list[str]:
    try:
        data = json.loads(CONFIG_ENDERECOS.read_text(encoding="utf-8"))
        return [
            str(value).strip()
            for value in data.get("enderecos_nao_disponiveis", [])
            if str(value).strip()
        ]
    except Exception:
        return []


def config_for(report_type: str) -> dict:
    if report_type not in PIPELINES:
        raise KeyError(f"Pipeline não configurado: {report_type}")
    return PIPELINES[report_type]


def get_state(report_type: str) -> dict:
    cfg = config_for(report_type)
    source_status, derived_meta = central.pipeline_state(
        cfg["sources"],
        cfg["derived_key"],
    )
    versions = central.source_versions(source_status, cfg["sources"])
    ready = central.all_sources_available(source_status, cfg["sources"])
    stale = ready and central.needs_reprocess(versions, derived_meta)
    return {
        "config": cfg,
        "sources": source_status,
        "derived": derived_meta,
        "versions": versions,
        "ready": ready,
        "stale": stale,
    }


def _download_sources(cfg: dict) -> dict[str, io.BytesIO]:
    keys = list(cfg["sources"])
    files: dict[str, io.BytesIO] = {}

    with ThreadPoolExecutor(max_workers=min(4, len(keys))) as executor:
        futures = {
            executor.submit(central.download_source, key): key
            for key in keys
        }
        for future in as_completed(futures):
            key = futures[future]
            file_obj, _ = future.result()
            files[key] = file_obj

    return files


def _process(report_type: str, files: dict[str, io.BytesIO]) -> dict:
    if report_type == "Relatório Geral":
        bruto = read_excel_safe(files["relatorio_geral"], sheet_name="Geral")
        for001 = read_excel_safe(files["for001"], sheet_name="PAINEL", header=4)
        for022 = read_excel_safe(files["for022"], sheet_name="Datas esperadas", header=0)
        return processar_relatorio_geral(bruto, for001, for022)

    if report_type == "Saldo em Estoque":
        analitico = read_excel_safe(files["analitico"], header=1)
        endereco = read_excel_safe(files["endereco"], header=1)
        return processar_estoque(
            analitico,
            endereco,
            _load_unavailable_addresses(),
        )

    if report_type == "Compras — S.C + P.C + Pré-nota":
        sc = read_excel_safe(files["sc"], header=1)

        pc_file = files["pc"]
        excel_pc = pd.ExcelFile(pc_file)
        sheet = "2-Pedido de Compras   Autoriz"
        if sheet not in excel_pc.sheet_names:
            raise ValueError(f"A planilha '{sheet}' não foi encontrada no P.C.")
        try:
            pc_file.seek(0)
        except Exception:
            pass
        pc = read_excel_safe(pc_file, sheet_name=sheet, header=1)
        pre_nota = read_excel_safe(files["pre_nota"], header=1)
        return processar_compras(sc, pc, pre_nota)

    if report_type == "MRP — TC/TP":
        pmp = read_excel_safe(files["pmp"])
        h001 = read_excel_safe(files["h001"])
        return processar_tc_tp(pmp, h001)

    raise KeyError(report_type)


def sync_pipeline(report_type: str, force: bool = False) -> dict:
    state = get_state(report_type)
    cfg = state["config"]

    if not state["ready"]:
        return {**state, "sync_status": "AGUARDANDO", "result": None}

    if not force and not state["stale"]:
        return {**state, "sync_status": "ATUALIZADO", "result": None}

    run_id = central.pipeline_start(cfg["pipeline_key"], state["versions"])

    try:
        files = _download_sources(cfg)
        result = _process(report_type, files)
        errors = list(result.get("erros") or [])

        if errors:
            central.pipeline_finish(
                run_id,
                "ERRO",
                rows_count=int(
                    len(result.get("tratado"))
                    if isinstance(result.get("tratado"), pd.DataFrame)
                    else 0
                ),
                message=" | ".join(str(item) for item in errors[:10]),
            )
            return {
                **state,
                "sync_status": "ERRO",
                "result": result,
            }

        treated = result.get("tratado")
        if not isinstance(treated, pd.DataFrame):
            raise RuntimeError("O conversor não retornou uma base tratada válida.")

        published = central.publish_derived(
            cfg["derived_key"],
            treated,
            state["versions"],
        )
        central.pipeline_finish(
            run_id,
            "CONCLUÍDO",
            rows_count=len(treated),
        )

        refreshed = {
            **state,
            "derived": {
                **published,
                "available": True,
            },
            "stale": False,
        }
        return {
            **refreshed,
            "sync_status": "PROCESSADO",
            "result": result,
            "published": published,
        }
    except Exception as exc:
        central.pipeline_finish(
            run_id,
            "ERRO",
            message=f"{type(exc).__name__}: {exc}",
        )
        return {
            **state,
            "sync_status": "ERRO",
            "result": None,
            "error": str(exc),
        }


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_current_frame(
    base_key: str,
    processed_at: str,
    source_versions_token: str,
) -> tuple[pd.DataFrame | None, dict]:
    try:
        return central.download_derived(base_key)
    except Exception:
        return None, {}


def current_frame(
    report_type: str,
    derived_meta: dict | None = None,
) -> tuple[pd.DataFrame | None, dict]:
    cfg = config_for(report_type)
    meta = derived_meta or {}

    processed_at = str(meta.get("processed_at") or "")
    versions = meta.get("source_versions") or {}
    token = json.dumps(
        versions,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )

    if not processed_at and not token:
        try:
            status = central.derived_status([cfg["derived_key"]])
            meta = status.get(cfg["derived_key"]) or {}
            processed_at = str(meta.get("processed_at") or "")
            versions = meta.get("source_versions") or {}
            token = json.dumps(
                versions,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
        except Exception:
            return None, {}

    return _cached_current_frame(
        cfg["derived_key"],
        processed_at,
        token,
    )


def clear_current_frame_cache() -> None:
    _cached_current_frame.clear()


def source_label(report_type: str, source_key: str) -> str:
    cfg = config_for(report_type)
    return str((cfg.get("labels") or {}).get(source_key) or source_key.upper())


def count_rows(file_name: str, raw: bytes) -> int:
    lower = file_name.lower()
    try:
        if lower.endswith(".csv"):
            return len(pd.read_csv(io.BytesIO(raw), sep=None, engine="python"))
        if lower.endswith((".xlsx", ".xls", ".xlsm", ".xltx")):
            return len(pd.read_excel(io.BytesIO(raw)))
    except Exception:
        return 0
    return 0
