from __future__ import annotations

import gzip
import io
import json
import os
from typing import Any

import pandas as pd
import requests
import streamlit as st
from supabase import create_client

DEFAULT_SUPABASE_URL = "https://cuixazpxkvniqldmmnth.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN1aXhhenB4a3ZuaXFsZG1tbnRoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc1MTYwNTMsImV4cCI6MjEwMzA5MjA1M30.jNFaIG1FcDYnMAoVaI23UYMuRL1BpZmuqu_LPEYb88E"
EDGE_URL = f"{DEFAULT_SUPABASE_URL}/functions/v1/setta-data-api"
BUCKET = "setta-data"


def _secret(*names: str) -> str:
    candidates: list[Any] = []
    try:
        for name in names:
            candidates.append(st.secrets.get(name))
        if "supabase" in st.secrets:
            supa = st.secrets["supabase"]
            for name in names:
                candidates.extend(
                    [
                        supa.get(name),
                        supa.get(name.lower()),
                        supa.get(name.replace("SUPABASE_", "").lower()),
                    ]
                )
    except Exception:
        pass

    for name in names:
        candidates.append(os.getenv(name))

    return next((str(value).strip() for value in candidates if value), "")


def supabase_url() -> str:
    return _secret("SUPABASE_URL") or DEFAULT_SUPABASE_URL


def supabase_key() -> str:
    return (
        _secret("SUPABASE_ANON_KEY", "SUPABASE_KEY", "SUPABASE_PUBLISHABLE_KEY")
        or DEFAULT_SUPABASE_ANON_KEY
    )


def api_url() -> str:
    return f"{supabase_url().rstrip('/')}/functions/v1/setta-data-api"


def _headers() -> dict[str, str]:
    key = supabase_key()
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
    }


def api_call(action: str, payload: dict | None = None, timeout: int = 60) -> dict:
    response = requests.post(
        api_url(),
        headers=_headers(),
        json={"action": action, "payload": payload or {}},
        timeout=timeout,
    )
    try:
        data = response.json()
    except Exception:
        data = {"ok": False, "error": response.text or f"HTTP {response.status_code}"}

    if not response.ok or not data.get("ok"):
        raise RuntimeError(data.get("error") or f"HTTP {response.status_code}")
    return data


def source_status(keys: list[str]) -> dict[str, dict]:
    rows = api_call("source_status", {"keys": keys}, timeout=30).get("data") or []
    return {str(row.get("source_key")): row for row in rows if isinstance(row, dict)}


def derived_status(keys: list[str]) -> dict[str, dict]:
    rows = api_call("derived_status", {"keys": keys}, timeout=30).get("data") or []
    return {str(row.get("base_key")): row for row in rows if isinstance(row, dict)}


def source_versions(status: dict[str, dict], keys: list[str]) -> dict[str, int]:
    return {
        key: int((status.get(key) or {}).get("version") or 0)
        for key in keys
    }


def all_sources_available(status: dict[str, dict], keys: list[str]) -> bool:
    return all(bool((status.get(key) or {}).get("available")) for key in keys)


def download_source(source_key: str, timeout: int = 120) -> tuple[io.BytesIO, dict]:
    meta = api_call("source_download", {"source_key": source_key}, timeout=30).get("data") or {}
    signed_url = str(meta.get("signed_url") or "")
    if not signed_url:
        raise RuntimeError(f"Fonte {source_key} sem URL de leitura.")

    response = requests.get(signed_url, timeout=timeout)
    response.raise_for_status()
    buffer = io.BytesIO(response.content)
    buffer.name = str(meta.get("last_file_name") or source_key)
    return buffer, meta


def upload_source(
    source_key: str,
    file_name: str,
    raw: bytes,
    rows_count: int = 0,
    mime_type: str = "application/octet-stream",
) -> dict:
    prepared = api_call(
        "source_upload_prepare",
        {"source_key": source_key},
        timeout=30,
    )
    path = str(prepared.get("path") or "")
    token = str(prepared.get("token") or "")
    if not path or not token:
        raise RuntimeError("A Central não retornou autorização para upload.")

    client = create_client(supabase_url(), supabase_key())
    client.storage.from_(BUCKET).upload_to_signed_url(
        path=path,
        token=token,
        file=io.BytesIO(raw),
    )

    return api_call(
        "source_commit",
        {
            "source_key": source_key,
            "file_name": file_name,
            "mime_type": mime_type,
            "rows_count": int(rows_count),
        },
        timeout=30,
    ).get("data") or {}


def dataframe_payload(frame: pd.DataFrame) -> bytes:
    text = frame.to_json(
        orient="table",
        date_format="iso",
        force_ascii=False,
        index=False,
    )
    return gzip.compress(text.encode("utf-8"), compresslevel=6)


def publish_derived(
    base_key: str,
    frame: pd.DataFrame,
    versions: dict[str, int],
) -> dict:
    raw = dataframe_payload(frame)
    prepared = api_call(
        "derived_upload_prepare",
        {"base_key": base_key},
        timeout=30,
    )
    path = str(prepared.get("path") or "")
    token = str(prepared.get("token") or "")
    if not path or not token:
        raise RuntimeError("A Central não retornou autorização para publicar a base.")

    client = create_client(supabase_url(), supabase_key())
    client.storage.from_(BUCKET).upload_to_signed_url(
        path=path,
        token=token,
        file=io.BytesIO(raw),
    )

    return api_call(
        "derived_commit",
        {
            "base_key": base_key,
            "rows_count": int(len(frame)),
            "source_versions": versions,
        },
        timeout=30,
    ).get("data") or {}


def download_derived(base_key: str, timeout: int = 120) -> tuple[pd.DataFrame, dict]:
    meta = api_call("derived_download", {"base_key": base_key}, timeout=30).get("data") or {}
    signed_url = str(meta.get("signed_url") or "")
    if not signed_url:
        raise RuntimeError(f"Base {base_key} sem URL de leitura.")

    response = requests.get(signed_url, timeout=timeout)
    response.raise_for_status()
    raw = gzip.decompress(response.content)
    frame = pd.read_json(io.BytesIO(raw), orient="table")
    return frame, meta


def needs_reprocess(
    source_version_map: dict[str, int],
    derived_meta: dict | None,
) -> bool:
    if not derived_meta or not derived_meta.get("available"):
        return True

    registered = derived_meta.get("source_versions") or {}
    normalized = {
        str(key): int(value or 0)
        for key, value in registered.items()
    }
    return normalized != {
        str(key): int(value or 0)
        for key, value in source_version_map.items()
    }


def pipeline_start(pipeline_key: str, versions: dict[str, int]) -> int | None:
    try:
        response = api_call(
            "pipeline_start",
            {"pipeline_key": pipeline_key, "source_versions": versions},
            timeout=30,
        )
        return int(response.get("run_id") or 0) or None
    except Exception:
        return None


def pipeline_finish(
    run_id: int | None,
    status: str,
    rows_count: int = 0,
    message: str = "",
) -> None:
    if not run_id:
        return
    try:
        api_call(
            "pipeline_finish",
            {
                "run_id": int(run_id),
                "status": status,
                "rows_count": int(rows_count),
                "message": message,
            },
            timeout=30,
        )
    except Exception:
        pass
