#!/usr/bin/env python3
"""Executa as quatro conversões da Central SETTA sem iniciar o Streamlit.

Uso: python scripts/sync_all_headless.py [--check] [--only TIPO]

A rotina só publica quando a versão das fontes muda ou quando a semana
operacional do TC/TP avança. Não altera as fontes recebidas.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# O script é chamado diretamente da pasta scripts/ no GitHub Actions.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def execute(pipelines, *, check: bool = False, only: str | None = None) -> int:
    names = [only] if only else list(pipelines.PIPELINES)
    failed = False
    for name in names:
        print(f"SETTA | Iniciando: {name}", flush=True)
        try:
            if check:
                state = pipelines.get_state(name)
                status = "PENDENTE" if state["stale"] else "ATUALIZADO"
                if not state["ready"]:
                    status = "AGUARDANDO_FONTES"
                print(json.dumps({
                    "relatorio": name,
                    "status": status,
                    "fontes_disponiveis": bool(state["ready"]),
                    "versoes_atuais": state["versions"],
                }, ensure_ascii=False, sort_keys=True), flush=True)
            else:
                result = pipelines.sync_pipeline(name, force=False)
                status = result.get("sync_status") or "ERRO"
                print(json.dumps({
                    "relatorio": name,
                    "status": status,
                    "versoes": result.get("versions") or {},
                    "registros": (
                        (result.get("published") or {}).get("rows_count")
                        or (result.get("derived") or {}).get("rows_count")
                        or 0
                    ),
                }, ensure_ascii=False, sort_keys=True), flush=True)
                if status not in {"PROCESSADO", "ATUALIZADO"}:
                    failed = True
                    print(f"SETTA | Atenção: {name} terminou como {status}", file=sys.stderr)
        except Exception as exc:
            failed = True
            # Erros são registrados nos logs do job; nenhuma credencial é impressa.
            print(f"SETTA | Falha em {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincronização autônoma das bases SETTA")
    parser.add_argument("--check", action="store_true", help="Somente verifica versões, sem publicar")
    parser.add_argument("--only", choices=[
        "Relatório Geral", "Saldo em Estoque",
        "Compras — S.C + P.C + Pré-nota", "MRP — TC/TP",
    ], help="Limita a execução ao processo informado")
    args = parser.parse_args()
    import pipeline_sync as pipelines
    return execute(pipelines, check=args.check, only=args.only)


if __name__ == "__main__":
    raise SystemExit(main())
