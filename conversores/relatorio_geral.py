from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import pandas as pd

COLUNAS_OBRIGATORIAS = [
    "Projeto",
    "Código",
    "Última solicitação",
    "Qtd. necessária",
    "Qtd. atendida",
    "Resp. separação",
    "Data de separação",
    "Resp. conferência",
    "Data de conferência",
]

COLUNAS_SAIDA = [
    "COD_MRP",
    "Projeto",
    "Código",
    "Última solicitação",
    "Qtd. necessária",
    "Qtd. atendida",
    "Pendência",
    "Resp. separação",
    "Data de separação",
    "Resp. conferência",
    "Data de conferência",
    "DATA MRP",
    "DATA CM",
    "SEMANA DE NECESSIDADE",
    "PERIODO DA SEMANA",
    "NECESSIDADE DA SEMANA",
]


def _texto(valor: Any) -> str:
    if pd.isna(valor):
        return ""
    return str(valor).strip()


def _normalizar_codigo(valor: Any, tamanho: int, nome: str, erros: list[str], linha: int) -> str:
    texto = _texto(valor)
    if not texto:
        erros.append(f"Linha {linha}: {nome} vazio.")
        return ""
    if re.fullmatch(r"\d+\.0", texto):
        texto = texto[:-2]
    if not texto.isdigit():
        erros.append(f"Linha {linha}: {nome} inválido ({texto!r}); esperado somente números.")
        return ""
    if len(texto) > tamanho:
        erros.append(f"Linha {linha}: {nome} possui {len(texto)} dígitos; máximo permitido: {tamanho}.")
        return ""
    return texto.zfill(tamanho)


def _normalizar_op(valor: Any) -> str:
    texto = _texto(valor)
    if not texto:
        return ""
    if re.fullmatch(r"\d+\.0", texto):
        texto = texto[:-2]
    return texto.zfill(11) if texto.isdigit() and len(texto) <= 11 else texto


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").fillna(0)


def _data(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, errors="coerce", dayfirst=True)


def _data_exibicao(valor: Any):
    if pd.isna(valor):
        return ""
    return pd.Timestamp(valor).strftime("%d/%m/%Y")


def _nomes_unicos(grupo: pd.Series) -> str:
    nomes = []
    for valor in grupo:
        texto = _texto(valor)
        if texto and texto not in nomes:
            nomes.append(texto)
    return " | ".join(nomes)


def _domingo_da_semana(data_referencia: date) -> date | None:
    primeiro_domingo = date(data_referencia.year, 1, 1)
    while primeiro_domingo.weekday() != 6:
        primeiro_domingo += timedelta(days=1)
    if data_referencia < primeiro_domingo:
        return None
    return data_referencia - timedelta(days=(data_referencia.weekday() + 1) % 7)


def _semana_operacional(valor: Any, hoje: date) -> tuple[str, str]:
    if pd.isna(valor):
        return "", ""

    data_original = pd.Timestamp(valor).date()
    primeiro_domingo = date(data_original.year, 1, 1)
    while primeiro_domingo.weekday() != 6:
        primeiro_domingo += timedelta(days=1)
    if data_original < primeiro_domingo:
        return "", ""

    data_calculo = hoje if data_original < hoje else data_original
    domingo = _domingo_da_semana(data_calculo)
    if domingo is None:
        return "", ""

    semana_numero = ((domingo - primeiro_domingo).days // 7) + 1
    sabado = domingo + timedelta(days=6)
    return f"{semana_numero:02d}", f"{domingo:%d/%m/%Y} a {sabado:%d/%m/%Y}"


def _mapa_for001(for001: pd.DataFrame, avisos: list[str]):
    # FOR-001: A = ORDEM DE PRODUÇÃO, M = DT MRP, N = CONDIÇÃO.
    # O vínculo é feito pela posição das colunas, conforme definição do relatório,
    # e não pelo texto do cabeçalho, evitando quebra por variação de nomenclatura.
    if for001.shape[1] < 14:
        return None, ["FOR-001: são necessárias pelo menos 14 colunas para acessar A, M e N."]

    base = for001.copy()
    base["_OP"] = base.iloc[:, 0].map(_normalizar_op)
    base["_DT_MRP"] = pd.to_datetime(base.iloc[:, 12], errors="coerce", dayfirst=True)
    base["_CONDICAO"] = base.iloc[:, 13].map(_texto).str.upper()
    base = base[base["_OP"] != ""].copy()

    registros = {}
    conflitos = 0
    for _, row in base.iterrows():
        op = row["_OP"]
        dt_mrp = row["_DT_MRP"]
        cond = row["_CONDICAO"]
        atual = registros.get(op)
        if atual is None:
            registros[op] = {"data_mrp": dt_mrp, "condicao": cond}
            continue

        if not pd.isna(dt_mrp) and (pd.isna(atual["data_mrp"]) or dt_mrp != atual["data_mrp"]):
            if not pd.isna(atual["data_mrp"]):
                conflitos += 1
            atual["data_mrp"] = dt_mrp

        if cond and cond != "-" and cond != atual["condicao"]:
            if atual["condicao"] and atual["condicao"] != "-":
                conflitos += 1
            atual["condicao"] = cond

    avisos.append(f"FOR-001: {len(registros):,} OP(s) válidas carregadas para vínculo.".replace(",", "."))
    if conflitos:
        avisos.append(f"FOR-001: {conflitos} ocorrência(s) de OP com mais de uma DATA MRP/CONDIÇÃO; foi mantido o último registro válido encontrado.")
    return registros, []


def _mapa_for022(for022: pd.DataFrame, avisos: list[str]):
    # FOR-022: A = OP e AJ = SEPARAÇÃO.
    # AJ é a 36ª coluna, índice 35.
    if for022.shape[1] < 36:
        return None, ["FOR-022: são necessárias pelo menos 36 colunas para acessar A e AJ."]

    base = for022.copy()
    base["_OP"] = base.iloc[:, 0].map(_normalizar_op)
    base["_SEPARACAO"] = pd.to_datetime(base.iloc[:, 35], errors="coerce", dayfirst=True)
    base = base[base["_OP"] != ""].copy()

    registros = {}
    for _, row in base.iterrows():
        op = row["_OP"]
        separacao = row["_SEPARACAO"]
        atual = registros.get(op)
        if atual is None:
            registros[op] = separacao
        elif pd.isna(atual) and not pd.isna(separacao):
            registros[op] = separacao
        elif not pd.isna(separacao) and not pd.isna(atual) and separacao > atual:
            registros[op] = separacao

    avisos.append(f"FOR-022: {len(registros):,} OP(s) válidas carregadas para vínculo.".replace(",", "."))
    return registros, []


def processar_relatorio_geral(
    bruto: pd.DataFrame,
    for001: pd.DataFrame | None = None,
    for022: pd.DataFrame | None = None,
) -> dict[str, Any]:
    erros: list[str] = []
    avisos: list[str] = []

    faltantes = [col for col in COLUNAS_OBRIGATORIAS if col not in bruto.columns]
    if faltantes:
        erros.append("Colunas obrigatórias ausentes: " + ", ".join(faltantes))
        return {
            "tratado": pd.DataFrame(),
            "validacao": pd.DataFrame({"Status": ["ERRO"], "Mensagem": erros}),
            "erros": erros,
            "avisos": avisos,
            "metricas": {"linhas_brutas": len(bruto), "chaves_unicas": 0, "linhas_agrupadas": 0, "erros": len(erros)},
        }

    if for001 is None or for022 is None:
        erros.append("É obrigatório informar os relatórios FOR-001 e FOR-022.")
        return {
            "tratado": pd.DataFrame(),
            "validacao": pd.DataFrame({"Status": ["ERRO"], "Mensagem": erros}),
            "erros": erros,
            "avisos": avisos,
            "metricas": {"linhas_brutas": len(bruto), "chaves_unicas": 0, "linhas_agrupadas": 0, "erros": len(erros)},
        }

    mapa001, erros001 = _mapa_for001(for001, avisos)
    mapa022, erros022 = _mapa_for022(for022, avisos)
    erros.extend(erros001 + erros022)
    if erros:
        return {
            "tratado": pd.DataFrame(),
            "validacao": pd.DataFrame({"Status": ["ERRO"], "Mensagem": erros}),
            "erros": erros,
            "avisos": avisos,
            "metricas": {"linhas_brutas": len(bruto), "chaves_unicas": 0, "linhas_agrupadas": 0, "erros": len(erros)},
        }

    df = bruto.copy()
    df.columns = [str(c).strip() for c in df.columns]

    projetos, materiais = [], []
    for pos, (projeto, codigo) in enumerate(zip(df["Projeto"], df["Código"]), start=2):
        projetos.append(_normalizar_codigo(projeto, 11, "Projeto", erros, pos))
        materiais.append(_normalizar_codigo(codigo, 8, "Código", erros, pos))

    df["Projeto"] = projetos
    df["Código"] = materiais
    df["COD_MRP"] = df["Projeto"] + "_" + df["Código"]
    df["Última solicitação"] = _data(df["Última solicitação"])
    df["Data de separação"] = _data(df["Data de separação"])
    df["Data de conferência"] = _data(df["Data de conferência"])
    df["Qtd. necessária"] = _numero(df["Qtd. necessária"])
    df["Qtd. atendida"] = _numero(df["Qtd. atendida"])

    duplicadas = int(df.duplicated("COD_MRP", keep=False).sum())
    grupos_duplicados = int(df.loc[df.duplicated("COD_MRP", keep=False), "COD_MRP"].nunique())
    if duplicadas:
        avisos.append(f"{duplicadas} linha(s) pertencem a {grupos_duplicados} COD_MRP duplicado(s) e foram agrupadas; nenhuma foi simplesmente excluída.")

    agrupado = (
        df.groupby("COD_MRP", sort=False, dropna=False)
        .agg(
            Projeto=("Projeto", "first"),
            Código=("Código", "first"),
            **{
                "Última solicitação": ("Última solicitação", "max"),
                "Qtd. necessária": ("Qtd. necessária", "sum"),
                "Qtd. atendida": ("Qtd. atendida", "sum"),
                "Resp. separação": ("Resp. separação", _nomes_unicos),
                "Data de separação": ("Data de separação", "max"),
                "Resp. conferência": ("Resp. conferência", _nomes_unicos),
                "Data de conferência": ("Data de conferência", "max"),
            },
        )
        .reset_index()
    )

    agrupado["Pendência"] = agrupado["Qtd. necessária"] - agrupado["Qtd. atendida"]
    agrupado["_OP"] = agrupado["Projeto"].map(_normalizar_op)

    agrupado["DATA MRP"] = agrupado["_OP"].map(
        lambda op: mapa001.get(op, {}).get("data_mrp", pd.NaT) if op else pd.NaT
    )
    agrupado["_CONDICAO_PCP"] = agrupado["_OP"].map(
        lambda op: mapa001.get(op, {}).get("condicao", "") if op else ""
    )
    agrupado["DATA CM"] = agrupado["_OP"].map(
        lambda op: mapa022.get(op, pd.NaT) if op else pd.NaT
    )

    def definir_semana(row):
        cond = _texto(row["_CONDICAO_PCP"]).upper()
        if cond == "NORMAL":
            semana, periodo = _semana_operacional(row["DATA MRP"], date.today())
            if semana:
                return semana, periodo
            return "SEM INFORMAÇÃO", ""
        if cond and cond != "-" and re.search(r"[A-ZÀ-Ý]", cond):
            return cond, ""
        return "SEM INFORMAÇÃO", ""

    semanas = agrupado.apply(definir_semana, axis=1)
    agrupado["SEMANA DE NECESSIDADE"] = semanas.map(lambda x: x[0])
    agrupado["PERIODO DA SEMANA"] = semanas.map(lambda x: x[1])

    # Somente demandas NORMAL entram no total semanal.
    agrupado["_DEMANDA_VALIDADA"] = agrupado["_CONDICAO_PCP"].eq("NORMAL")
    agrupado["NECESSIDADE DA SEMANA"] = 0.0
    mask_normal = agrupado["_DEMANDA_VALIDADA"] & agrupado["SEMANA DE NECESSIDADE"].str.match(r"^\d{2}$", na=False)
    if mask_normal.any():
        agrupado.loc[mask_normal, "NECESSIDADE DA SEMANA"] = (
            agrupado.loc[mask_normal]
            .groupby(["Código", "SEMANA DE NECESSIDADE"])["Qtd. necessária"]
            .transform("sum")
        )

    sem_op = agrupado["_OP"].eq("") | ~agrupado["_OP"].isin(mapa001.keys())
    if sem_op.any():
        avisos.append(f"{int(sem_op.sum())} linha(s) do Relatório Geral não tiveram a OP identificada no FOR-001.")

    sem_cm = agrupado["_OP"].eq("") | ~agrupado["_OP"].isin(mapa022.keys())
    if sem_cm.any():
        avisos.append(f"{int(sem_cm.sum())} linha(s) não tiveram a OP identificada no FOR-022; DATA CM = NI.")

    agrupado["DATA MRP"] = agrupado["DATA MRP"].map(
        lambda x: _data_exibicao(x) if not pd.isna(x) else "SEM INFORMAÇÃO"
    )
    agrupado["DATA CM"] = agrupado["DATA CM"].map(
        lambda x: _data_exibicao(x) if not pd.isna(x) else "NI"
    )
    agrupado = agrupado[COLUNAS_SAIDA]

    for col in ["Última solicitação", "Data de separação", "Data de conferência"]:
        agrupado[col] = agrupado[col].map(_data_exibicao)

    validacoes = []
    for cod, grupo in agrupado.groupby("COD_MRP", sort=False):
        validacoes.append(
            {
                "COD_MRP": cod,
                "Projeto válido": bool(re.fullmatch(r"\d{11}", str(grupo.iloc[0]["Projeto"]))),
                "Código válido": bool(re.fullmatch(r"\d{8}", str(grupo.iloc[0]["Código"]))),
                "Pendência recalculada": True,
            }
        )
    validacao = pd.DataFrame(validacoes)

    invalidos = int((~validacao["Projeto válido"]).sum()) + int((~validacao["Código válido"]).sum())
    if invalidos:
        erros.append(f"{invalidos} validação(ões) de código falharam após a conversão.")

    metricas = {
        "linhas_brutas": len(bruto),
        "chaves_unicas": int(df["COD_MRP"].nunique()),
        "linhas_agrupadas": len(agrupado),
        "erros": len(erros),
    }

    return {
        "tratado": agrupado,
        "validacao": validacao,
        "erros": erros,
        "avisos": avisos,
        "metricas": metricas,
    }
