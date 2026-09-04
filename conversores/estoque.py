from __future__ import annotations

import re
from typing import Any

import pandas as pd


COLUNAS_ANALITICO = ["CODIGO", "DESCRICAO", "SALDO EM ESTOQUE"]
COLUNAS_ENDERECO = ["Produto", "Endereco", "Quantidade"]
COLUNAS_SAIDA = [
    "COD_MATERIAL",
    "DESCRICAO",
    "SALDO_EM_ESTOQUE",
    "SALDO_NAO_DISPONIVEL",
    "SALDO_DISPONIVEL",
]


def _texto(valor: Any) -> str:
    if pd.isna(valor):
        return ""
    return str(valor).strip()


def _normalizar_codigo(valor: Any, erros: list[str], linha: int, origem: str) -> str:
    texto = _texto(valor)
    if not texto:
        erros.append(f"{origem} - linha {linha}: código do produto vazio.")
        return ""

    if re.fullmatch(r"\d+\.0", texto):
        texto = texto[:-2]

    if not texto.isdigit():
        erros.append(f"{origem} - linha {linha}: código inválido ({texto!r}); esperado somente números.")
        return ""

    if len(texto) > 8:
        erros.append(f"{origem} - linha {linha}: código possui {len(texto)} dígitos; máximo permitido: 8.")
        return ""

    return texto.zfill(8)


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").fillna(0)


def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    resultado = df.copy()
    resultado.columns = [str(c).strip() for c in resultado.columns]
    return resultado


def preparar_analitico(bruto: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Lê a estrutura do Analítico e consolida uma linha por produto."""
    erros: list[str] = []
    df = _normalizar_colunas(bruto)

    faltantes = [c for c in COLUNAS_ANALITICO if c not in df.columns]
    if faltantes:
        return pd.DataFrame(), ["Analítico: colunas obrigatórias ausentes: " + ", ".join(faltantes)]

    codigos = []
    for pos, valor in enumerate(df["CODIGO"], start=2):
        codigos.append(_normalizar_codigo(valor, erros, pos, "Analítico"))
    df["COD_MATERIAL"] = codigos
    df["SALDO EM ESTOQUE"] = _numero(df["SALDO EM ESTOQUE"])

    # O Analítico é a base. Se o ERP repetir um produto em mais de um armazém,
    # os saldos são somados e a descrição é preservada.
    agrupado = (
        df[df["COD_MATERIAL"] != ""]
        .groupby("COD_MATERIAL", sort=False, as_index=False)
        .agg(
            DESCRICAO=("DESCRICAO", "first"),
            SALDO_EM_ESTOQUE=("SALDO EM ESTOQUE", "sum"),
        )
    )
    return agrupado, erros


def preparar_endereco(bruto: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Lê o relatório de Endereço e soma quantidade por produto/endereço."""
    erros: list[str] = []
    df = _normalizar_colunas(bruto)

    faltantes = [c for c in COLUNAS_ENDERECO if c not in df.columns]
    if faltantes:
        return pd.DataFrame(), ["Endereço: colunas obrigatórias ausentes: " + ", ".join(faltantes)]

    codigos = []
    for pos, valor in enumerate(df["Produto"], start=2):
        codigos.append(_normalizar_codigo(valor, erros, pos, "Endereço"))
    df["COD_MATERIAL"] = codigos
    df["Endereco"] = df["Endereco"].map(_texto)
    df["Quantidade"] = _numero(df["Quantidade"])

    # Repetições do mesmo produto no mesmo endereço são somadas; nunca excluídas.
    agrupado = (
        df[(df["COD_MATERIAL"] != "") & (df["Endereco"] != "")]
        .groupby(["COD_MATERIAL", "Endereco"], sort=False, as_index=False)["Quantidade"]
        .sum()
    )
    return agrupado, erros


def processar_estoque(
    analitico_bruto: pd.DataFrame,
    endereco_bruto: pd.DataFrame,
    enderecos_nao_disponiveis: list[str],
) -> dict[str, Any]:
    erros: list[str] = []
    avisos: list[str] = []

    analitico, erros_analitico = preparar_analitico(analitico_bruto)
    endereco, erros_endereco = preparar_endereco(endereco_bruto)
    erros.extend(erros_analitico)
    erros.extend(erros_endereco)

    if analitico.empty:
        erros.append("Analítico: nenhum produto válido foi encontrado após a padronização.")
    if endereco.empty and not erros_endereco:
        avisos.append("Endereço: nenhum registro válido foi encontrado.")

    if erros:
        return {
            "tratado": pd.DataFrame(),
            "enderecos": pd.DataFrame(),
            "validacao": pd.DataFrame({"Status": ["ERRO"], "Mensagem": erros}),
            "erros": erros,
            "avisos": avisos,
            "metricas": {
                "linhas_analitico": len(analitico_bruto),
                "linhas_endereco": len(endereco_bruto),
                "produtos_analitico": len(analitico),
                "produtos_endereco": int(endereco["COD_MATERIAL"].nunique()) if not endereco.empty else 0,
                "inconsistencias": 0,
                "erros": len(erros),
            },
        }

    selecionados = {_texto(x) for x in enderecos_nao_disponiveis if _texto(x)}
    enderecos_disponiveis_lista = sorted(endereco["Endereco"].dropna().unique().tolist())
    desconhecidos = sorted(selecionados - set(enderecos_disponiveis_lista))
    if desconhecidos:
        avisos.append(
            "Endereço(s) marcado(s) como não disponível(is) que não aparecem neste arquivo: "
            + ", ".join(desconhecidos)
        )

    nao_disp = endereco[endereco["Endereco"].isin(selecionados)]
    nao_disp_por_produto = (
        nao_disp.groupby("COD_MATERIAL", as_index=False)["Quantidade"].sum()
        .rename(columns={"Quantidade": "SALDO_NAO_DISPONIVEL"})
    )

    tratado = analitico.merge(nao_disp_por_produto, on="COD_MATERIAL", how="left")
    tratado["SALDO_NAO_DISPONIVEL"] = tratado["SALDO_NAO_DISPONIVEL"].fillna(0)

    # O Analítico é sempre a base. Se o endereço indicar mais indisponível que
    # o saldo total, sinalizamos a inconsistência, mas o saldo disponível nunca
    # ultrapassa a base nem fica negativo.
    mascara_inconsistencia = tratado["SALDO_NAO_DISPONIVEL"] > tratado["SALDO_EM_ESTOQUE"]
    qtd_inconsistencias = int(mascara_inconsistencia.sum())
    if qtd_inconsistencias:
        avisos.append(
            f"{qtd_inconsistencias} produto(s) possuem quantidade em endereços não disponíveis "
            "maior que o saldo do Analítico. O Analítico foi mantido como base e o saldo disponível "
            "foi limitado a zero nesses casos."
        )

    tratado["SALDO_DISPONIVEL"] = (
        tratado["SALDO_EM_ESTOQUE"] - tratado["SALDO_NAO_DISPONIVEL"]
    ).clip(lower=0)
    tratado = tratado[COLUNAS_SAIDA]

    # Produtos que aparecem no Endereço mas não existem no Analítico.
    produtos_endereco = set(endereco["COD_MATERIAL"])
    produtos_analitico = set(analitico["COD_MATERIAL"])
    somente_endereco = sorted(produtos_endereco - produtos_analitico)
    if somente_endereco:
        avisos.append(
            f"{len(somente_endereco)} produto(s) aparecem no Endereço mas não no Analítico. "
            "Eles não entram no saldo disponível, pois o Analítico é a base."
        )

    validacao = tratado.copy()
    validacao["Saldo disponível válido"] = validacao["SALDO_DISPONIVEL"] >= 0
    validacao["Base"] = "Analítico"
    validacao["Inconsistência endereço > analítico"] = mascara_inconsistencia.values

    metricas = {
        "linhas_analitico": len(analitico_bruto),
        "linhas_endereco": len(endereco_bruto),
        "produtos_analitico": len(analitico),
        "produtos_endereco": int(endereco["COD_MATERIAL"].nunique()),
        "inconsistencias": qtd_inconsistencias,
        "erros": len(erros),
    }

    return {
        "tratado": tratado,
        "enderecos": endereco,
        "validacao": validacao,
        "erros": erros,
        "avisos": avisos,
        "metricas": metricas,
    }
