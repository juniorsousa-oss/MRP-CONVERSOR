"""Adaptação do JSON MES GeneralReport ao Relatório Geral do Conversor MRP.

Este módulo NÃO publica/atualiza nenhuma base. Ele prepara um DataFrame com
os 10 campos esperados por processar_relatorio_geral, preservando as demais
fontes FOR001, FOR022 e CADASTROS no pipeline habitual.

A API retorna registros de material/lote. Não agrupar nesta etapa:
necessidade e atendimento possuem regras específicas no conversor.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Mapping

import pandas as pd

from conversores.semanas import interpretar_data_setta

MES_TO_GERAL = {
    "OP": "Projeto",
    "Code": "Código",
    "Description": "Descrição",
    "LastRequest": "Última solicitação",
    "NecessaryQuantity": "Qtd. necessária",
    "AttendedQuantity": "Qtd. atendida",
    "SeparationUser": "Resp. separação",
    "SeparationDate": "Data de separação",
    "ConferenceResponse": "Resp. conferência",
    "ConferenceDate": "Data de conferência",
}
# Campos mínimos para a demanda não ser silenciosamente subestimada.
CAMPOS_CRITICOS = ("OP", "Code", "NecessaryQuantity", "AttendedQuantity")
COLUNAS = list(MES_TO_GERAL.values())


def _registros(payload: Any) -> list[dict]:
    """Contrato visto na resposta do Teams: array JSON de objetos.

    Alguns gateways colocam o array em data/items/results; esses formatos
    precisam manter exatamente a mesma estrutura de registro.
    """
    if isinstance(payload, dict):
        encontrados = [payload[k] for k in ("data", "items", "results") if isinstance(payload.get(k), list)]
        if len(encontrados) != 1:
            raise ValueError("JSON MES não contém uma lista única de registros em data/items/results.")
        payload = encontrados[0]
    if not isinstance(payload, list) or not payload:
        raise ValueError("JSON MES vazio ou com estrutura de registros inesperada.")
    if any(not isinstance(item, dict) for item in payload):
        raise ValueError("JSON MES possui registros que não são objetos.")
    return payload


def _id_numero(valor: Any, limite: int, nome: str, indice: int) -> str:
    """Preserva zeros à esquerda, sem transformar 00000441 em 441."""
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"Linha {indice}: {nome} ausente.")
    texto = str(valor).strip()
    if re.fullmatch(r"\d+\.0", texto):
        texto = texto[:-2]
    if not texto.isdigit() or len(texto) > limite:
        raise ValueError(f"Linha {indice}: {nome} inválido.")
    return texto.zfill(limite)


def _quantidade(valor: Any, nome: str, indice: int) -> float:
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"Linha {indice}: {nome} ausente.")
    texto = str(valor).strip()
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        n = float(Decimal(texto))
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError(f"Linha {indice}: {nome} não é numérico.") from None
    if not math.isfinite(n) or n < 0:
        raise ValueError(f"Linha {indice}: {nome} fora da faixa válida.")
    return n


def _data(valor: Any) -> str:
    """ISO UTC da API -> dia operacional em America/Sao_Paulo.

    O Excel de entrada atual considera datas brasileiras, e não o fuso UTC.
    A interpretação dos horários para distinguir solicitações repetidas no
    mesmo dia deve ser homologada antes do uso automático da API.
    """
    if valor is None or str(valor).strip() == "":
        return ""
    texto = str(valor).strip()
    if "T" in texto and re.search(r"(Z|[+-]\d{2}:?\d{2})$", texto, re.I):
        stamp = pd.to_datetime(texto, errors="coerce", utc=True)
        if pd.isna(stamp):
            raise ValueError("Data MES inválida.")
        return stamp.tz_convert("America/Sao_Paulo").strftime("%d/%m/%Y")
    data = interpretar_data_setta(valor)
    if pd.isna(data):
        raise ValueError("Data MES inválida.")
    return pd.Timestamp(data).strftime("%d/%m/%Y")


def adaptar_json_mes(payload: Any) -> pd.DataFrame:
    """Valida e mapeia registros completos, sem eliminar linhas nem somar lotes."""
    registros = _registros(payload)
    linhas = []
    for indice, item in enumerate(registros, 1):
        faltam = [k for k in CAMPOS_CRITICOS if k not in item or item[k] is None]
        if faltam:
            raise ValueError(f"Linha {indice}: campos críticos ausentes: {', '.join(faltam)}.")

        linha = {
            "Projeto": _id_numero(item["OP"], 11, "OP", indice),
            "Código": _id_numero(item["Code"], 8, "Code", indice),
            "Descrição": str(item.get("Description") or "").strip(),
            "Última solicitação": _data(item.get("LastRequest")),
            "Qtd. necessária": _quantidade(item["NecessaryQuantity"], "NecessaryQuantity", indice),
            "Qtd. atendida": _quantidade(item["AttendedQuantity"], "AttendedQuantity", indice),
            "Resp. separação": str(item.get("SeparationUser") or "").strip(),
            "Data de separação": _data(item.get("SeparationDate")),
            "Resp. conferência": str(item.get("ConferenceResponse") or "").strip(),
            "Data de conferência": _data(item.get("ConferenceDate")),
        }
        linhas.append(linha)
    df = pd.DataFrame(linhas, columns=COLUNAS)
    if df.empty or df["Código"].eq("").any() or df["Projeto"].eq("").any():
        raise ValueError("Relatório Geral MES inválido ou sem materiais.")
    return df


def adaptar_json_mes_com_quarentena(
    payload: Any, *, linhas_referencia: int | None = None,
    max_excecoes_pct: float = 0.5, minimo_referencia_pct: float = 80.0,
) -> dict:
    """Separa registros inválidos sem travar os materiais válidos.

    Este adaptador somente prepara dados em memória. A publicação é tarefa
    exclusiva do pipeline transacional após validar os critérios de proteção.
    A quarentena deve ser publicada/armazenada junto com a fonte tratada,
    jamais apagada silenciosamente.
    """
    registros = _registros(payload)
    linhas_validas = []
    excecoes = []
    for indice, item in enumerate(registros, 1):
        try:
            faltam = [
                k for k in CAMPOS_CRITICOS
                if k not in item or item[k] is None
                or (isinstance(item[k], str) and item[k].strip() == "")
            ]
            if faltam:
                raise ValueError("Campos ausentes: " + ", ".join(faltam))
            linha = {
                "Projeto": _id_numero(item["OP"], 11, "OP", indice),
                "Código": _id_numero(item["Code"], 8, "Code", indice),
                "Descrição": str(item.get("Description") or "").strip(),
                "Última solicitação": _data(item.get("LastRequest")),
                "Qtd. necessária": _quantidade(item["NecessaryQuantity"], "NecessaryQuantity", indice),
                "Qtd. atendida": _quantidade(item["AttendedQuantity"], "AttendedQuantity", indice),
                "Resp. separação": str(item.get("SeparationUser") or "").strip(),
                "Data de separação": _data(item.get("SeparationDate")),
                "Resp. conferência": str(item.get("ConferenceResponse") or "").strip(),
                "Data de conferência": _data(item.get("ConferenceDate")),
            }
            linhas_validas.append(linha)
        except ValueError as exc:
            # Os campos abaixo ficam apenas na tabela restrita de correções,
            # nunca nos indicadores públicos do Monitor.
            excecoes.append({
                "Linha JSON": indice,
                "Projeto informado": str(item.get("OP") or "").strip(),
                "Código informado": str(item.get("Code") or "").strip(),
                "Descrição": str(item.get("Description") or "").strip(),
                "Qtd. necessária informada": item.get("NecessaryQuantity"),
                "Qtd. atendida informada": item.get("AttendedQuantity"),
                "Motivo": str(exc),
                "Status": "PENDENTE DE REGULARIZAÇÃO",
            })

    validos = pd.DataFrame(linhas_validas, columns=COLUNAS)
    pendentes = pd.DataFrame(excecoes, columns=[
        "Linha JSON", "Projeto informado", "Código informado", "Descrição",
        "Qtd. necessária informada", "Qtd. atendida informada",
        "Motivo", "Status",
    ])
    total = len(registros)
    pct = 100.0 * len(pendentes) / total
    motivos_protecao = []
    if validos.empty:
        motivos_protecao.append("Nenhum registro de material válido na resposta.")
    if pct > max_excecoes_pct:
        motivos_protecao.append(
            "Percentual de inconsistências acima do limite de segurança."
        )
    if linhas_referencia and linhas_referencia > 0:
        if 100.0 * total / linhas_referencia < minimo_referencia_pct:
            motivos_protecao.append(
                "Volume da resposta muito inferior à última fonte válida."
            )
    situacao = (
        "PROTEGER_BASE" if motivos_protecao
        else "PROCESSAR_COM_RESSALVAS" if not pendentes.empty
        else "PROCESSAR"
    )
    return {
        "tratado": validos,
        "inconsistencias": pendentes,
        "status": situacao,
        "pode_processar": not motivos_protecao,
        "motivos_protecao": motivos_protecao,
        "metricas": {
            "linhas_recebidas": total,
            "linhas_validas": len(validos),
            "linhas_quarentena": len(pendentes),
            "percentual_inconsistencias": round(pct, 4),
        },
    }


def exportar_geral_excel(frame: pd.DataFrame) -> bytes:
    """Gera planilha compatível com a aba 'Geral' do fluxo atual."""
    if frame.empty or list(frame.columns) != COLUNAS:
        raise ValueError("Schema do Relatório Geral incompatível com o Conversor.")
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Geral", index=False)
    return buffer.getvalue()


def diagnostico_mes(frame: pd.DataFrame) -> dict:
    """Somente estatísticas agregadas, sem OP, nomes ou dados pessoais."""
    return {
        "linhas": int(len(frame)),
        "ops": int(frame["Projeto"].nunique()),
        "materiais": int(frame["Código"].nunique()),
        "op_material": int(frame[["Projeto", "Código"]].drop_duplicates().shape[0]),
        "necessidade_linhas": float(frame["Qtd. necessária"].sum()),
        "atendimento_linhas": float(frame["Qtd. atendida"].sum()),
        "datas_solicitacao_ausentes": int(frame["Última solicitação"].eq("").sum()),
    }
