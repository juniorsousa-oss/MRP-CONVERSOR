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

    # Excel costuma carregar códigos numéricos como 123.0.
    if re.fullmatch(r"\d+\.0", texto):
        texto = texto[:-2]

    if not texto.isdigit():
        erros.append(f"Linha {linha}: {nome} inválido ({texto!r}); esperado somente números.")
        return ""

    if len(texto) > tamanho:
        erros.append(f"Linha {linha}: {nome} possui {len(texto)} dígitos; máximo permitido: {tamanho}.")
        return ""

    return texto.zfill(tamanho)


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").fillna(0)


def _data(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, errors="coerce", dayfirst=True)


def _ultima_data(grupo: pd.Series):
    datas = pd.to_datetime(grupo, errors="coerce", dayfirst=True).dropna()
    return datas.max() if not datas.empty else pd.NaT


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
    """Retorna o domingo da semana operacional (domingo a sábado).

    Datas anteriores ao primeiro domingo do ano são desconsideradas.
    """
    primeiro_domingo = date(data_referencia.year, 1, 1)
    while primeiro_domingo.weekday() != 6:  # domingo = 6
        primeiro_domingo += timedelta(days=1)

    if data_referencia < primeiro_domingo:
        return None

    return data_referencia - timedelta(days=(data_referencia.weekday() + 1) % 7)


def _semana_operacional(valor: Any, hoje: date) -> tuple[str, str]:
    """Calcula semana e período pela regra do MRP.

    - Domingo inicia e sábado encerra a semana.
    - Datas anteriores a hoje usam a semana atual.
    - A data original permanece intacta no relatório.
    - Datas anteriores ao primeiro domingo do ano não recebem semana.
    """
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

    # A semana é numerada a partir do primeiro domingo do ano.
    semana_numero = ((domingo - primeiro_domingo).days // 7) + 1
    sabado = domingo + timedelta(days=6)

    return f"{semana_numero:02d}", f"{domingo:%d/%m/%Y} a {sabado:%d/%m/%Y}"


def processar_relatorio_geral(bruto: pd.DataFrame) -> dict[str, Any]:
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
            "metricas": {
                "linhas_brutas": len(bruto),
                "chaves_unicas": 0,
                "linhas_agrupadas": 0,
                "erros": len(erros),
            },
        }

    df = bruto.copy()
    df.columns = [str(c).strip() for c in df.columns]

    projetos = []
    materiais = []
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

    if df["Última solicitação"].isna().any():
        avisos.append(f"{int(df['Última solicitação'].isna().sum())} linha(s) sem data de última solicitação.")

    duplicadas = int(df.duplicated("COD_MRP", keep=False).sum())
    grupos_duplicados = int(df.loc[df.duplicated("COD_MRP", keep=False), "COD_MRP"].nunique())
    if duplicadas:
        avisos.append(
            f"{duplicadas} linha(s) pertencem a {grupos_duplicados} COD_MRP duplicado(s) e foram agrupadas; nenhuma foi simplesmente excluída."
        )

    # Uma linha por Projeto + Material. Lote não participa desta primeira versão.
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

    # A semana de necessidade é determinada pela Última solicitação.
    # Se a data já passou, usa-se a semana atual; a data original não é alterada.
    hoje = date.today()
    semanas = agrupado["Última solicitação"].map(lambda x: _semana_operacional(x, hoje))
    agrupado["SEMANA DE NECESSIDADE"] = semanas.map(lambda x: x[0])
    agrupado["PERIODO DA SEMANA"] = semanas.map(lambda x: x[1])

    # Soma da demanda do mesmo item (Código) dentro da semana de necessidade.
    agrupado["NECESSIDADE DA SEMANA"] = (
        agrupado.groupby(["Código", "SEMANA DE NECESSIDADE"], dropna=False)["Qtd. necessária"]
        .transform("sum")
    )

    agrupado = agrupado[COLUNAS_SAIDA]

    # Datas em formato de Excel amigável.
    for col in ["Última solicitação", "Data de separação", "Data de conferência"]:
        agrupado[col] = agrupado[col].map(_data_exibicao)

    # Validações do resultado final.
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
