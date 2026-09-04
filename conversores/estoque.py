from __future__ import annotations

import re
from typing import Any

import pandas as pd


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
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce").fillna(0)
    texto = serie.astype(str).str.strip().str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(texto, errors="coerce").fillna(0)


def _validar_posicoes(df: pd.DataFrame, quantidade_colunas: int, origem: str) -> list[str]:
    if df.shape[1] < quantidade_colunas:
        return [f"{origem}: o arquivo possui {df.shape[1]} coluna(s), mas são necessárias pelo menos {quantidade_colunas}."]
    return []


def preparar_analitico(bruto: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    erros: list[str] = []
    faltantes = _validar_posicoes(bruto, 8, "Analítico")
    if faltantes:
        return pd.DataFrame(), faltantes

    df = pd.DataFrame({
        "COD_MATERIAL_BRUTO": bruto.iloc[:, 0],
        "DESCRICAO": bruto.iloc[:, 3],
        "SALDO_EM_ESTOQUE": bruto.iloc[:, 7],
    })

    df["COD_MATERIAL"] = [
        _normalizar_codigo(valor, erros, pos, "Analítico")
        for pos, valor in enumerate(df["COD_MATERIAL_BRUTO"], start=2)
    ]
    df["SALDO_EM_ESTOQUE"] = _numero(df["SALDO_EM_ESTOQUE"])

    agrupado = (
        df[df["COD_MATERIAL"] != ""]
        .groupby("COD_MATERIAL", sort=False, as_index=False)
        .agg(
            DESCRICAO=("DESCRICAO", lambda s: next((x for x in map(_texto, s) if x), "")),
            SALDO_EM_ESTOQUE=("SALDO_EM_ESTOQUE", "sum"),
        )
    )
    return agrupado, erros


def preparar_endereco(bruto: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    erros: list[str] = []
    faltantes = _validar_posicoes(bruto, 8, "Endereço")
    if faltantes:
        return pd.DataFrame(), faltantes

    df = pd.DataFrame({
        "COD_MATERIAL_BRUTO": bruto.iloc[:, 0],
        "Endereco": bruto.iloc[:, 3],
        "Quantidade": bruto.iloc[:, 7],
    })

    df["COD_MATERIAL"] = [
        _normalizar_codigo(valor, erros, pos, "Endereço")
        for pos, valor in enumerate(df["COD_MATERIAL_BRUTO"], start=2)
    ]
    df["Endereco"] = df["Endereco"].map(_texto)
    df["Quantidade"] = _numero(df["Quantidade"])

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

    if analitico.empty and not erros_analitico:
        erros.append("Analítico: nenhum produto válido foi encontrado após a padronização.")
    if endereco.empty and not erros_endereco:
        avisos.append("Endereço: nenhum registro válido foi encontrado.")

    if erros:
        return {
            "tratado": pd.DataFrame(),
            "enderecos": pd.DataFrame(),
            "validacao": pd.DataFrame({"Status": ["ERRO"] * len(erros), "Mensagem": erros}),
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
    enderecos_presentes = set(endereco["Endereco"].dropna().unique().tolist()) if not endereco.empty else set()
    desconhecidos = sorted(selecionados - enderecos_presentes)
    if desconhecidos:
        avisos.append(
            "INCONSISTÊNCIA | Relatório com problema: ENDEREÇO | "
            "Endereço(s) marcado(s) como NÃO DISPONÍVEL, mas ausente(s) neste relatório: "
            + ", ".join(desconhecidos)
        )

    # REGRA FUNDAMENTAL:
    # somente os endereços explicitamente marcados pelo usuário como NÃO DISPONÍVEIS
    # podem compor SALDO_NAO_DISPONIVEL. Nenhum outro endereço é abatido.
    nao_disp = endereco[endereco["Endereco"].isin(selecionados)].copy()

    nao_disp_por_produto = (
        nao_disp.groupby("COD_MATERIAL", as_index=False)["Quantidade"]
        .sum()
        .rename(columns={"Quantidade": "SALDO_NAO_DISPONIVEL"})
    )

    tratado = analitico.merge(nao_disp_por_produto, on="COD_MATERIAL", how="left")
    tratado["SALDO_NAO_DISPONIVEL"] = tratado["SALDO_NAO_DISPONIVEL"].fillna(0)

    # A 4ª coluna é exatamente a soma das quantidades do relatório ENDEREÇO
    # para os endereços marcados como NÃO DISPONÍVEIS, por código de material.
    mascara_inconsistencia = tratado["SALDO_NAO_DISPONIVEL"] > tratado["SALDO_EM_ESTOQUE"]
    qtd_inconsistencias = int(mascara_inconsistencia.sum())

    if qtd_inconsistencias:
        for _, row in tratado.loc[mascara_inconsistencia].iterrows():
            codigo = row["COD_MATERIAL"]
            enderecos_problema = nao_disp.loc[
                nao_disp["COD_MATERIAL"] == codigo,
                ["Endereco", "Quantidade"],
            ]
            detalhes_enderecos = "; ".join(
                f"{r.Endereco}={r.Quantidade:g}" for r in enderecos_problema.itertuples(index=False)
            )
            avisos.append(
                "INCONSISTÊNCIA | Relatórios com problema: ANALÍTICO + ENDEREÇO | "
                f"Código: {codigo} | "
                f"Analítico (Saldo em Estoque): {row['SALDO_EM_ESTOQUE']:g} | "
                f"Endereço (soma dos marcados como NÃO DISPONÍVEIS): {row['SALDO_NAO_DISPONIVEL']:g} | "
                f"Endereços considerados: {detalhes_enderecos} | "
                "Regra aplicada: o Analítico é a base e o Saldo Disponível fica em 0."
            )

    # O Analítico é sempre a base. Nunca permitir saldo disponível negativo.
    tratado["SALDO_DISPONIVEL"] = (
        tratado["SALDO_EM_ESTOQUE"] - tratado["SALDO_NAO_DISPONIVEL"]
    ).clip(lower=0)
    tratado = tratado[COLUNAS_SAIDA]

    produtos_endereco = set(endereco["COD_MATERIAL"]) if not endereco.empty else set()
    produtos_analitico = set(analitico["COD_MATERIAL"])
    somente_endereco = sorted(produtos_endereco - produtos_analitico)
    if somente_endereco:
        avisos.append(
            "INCONSISTÊNCIA | Relatório com problema: ENDEREÇO | "
            f"{len(somente_endereco)} código(s) aparecem no Endereço mas não no Analítico | "
            f"Códigos: {', '.join(somente_endereco)} | "
            "Regra aplicada: esses códigos não entram no estoque tratado, pois o Analítico é a base."
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
