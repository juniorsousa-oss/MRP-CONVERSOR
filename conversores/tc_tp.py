import re
import unicodedata
from datetime import date, timedelta

import pandas as pd

from conversores.semanas import semana_operacional


def _texto(valor):
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _normalizar_texto(valor):
    texto = _texto(valor)
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"\s+", " ", texto).strip().upper()
    return texto


def _codigo(valor):
    texto = _texto(valor)
    if not texto:
        return ""
    try:
        return str(int(float(texto))).zfill(8)
    except (TypeError, ValueError):
        return texto


def _data(valor):
    if pd.isna(valor) or _texto(valor) == "":
        return pd.NaT
    return pd.to_datetime(valor, errors="coerce", dayfirst=True)


def _semana(valor, hoje=None):
    """Identifica a semana pelo ano do domingo inicial; datas vencidas vão à semana atual."""
    return semana_operacional(valor, hoje)


def _localizar_coluna(df, aliases, fallback_idx=None):
    aliases_norm = {_normalizar_texto(x) for x in aliases}

    for idx, coluna in enumerate(df.columns):
        if _normalizar_texto(coluna) in aliases_norm:
            return idx

    if fallback_idx is not None and 0 <= fallback_idx < df.shape[1]:
        return fallback_idx

    raise ValueError(
        "Não foi possível localizar uma coluna obrigatória. "
        f"Esperado um dos cabeçalhos: {', '.join(aliases)}."
    )


def _status_programado(valor):
    return _normalizar_texto(valor).startswith("PROGRAMAD")


def _colunas_pmp(pmp):
    """
    Layout atual do PMP:
    A OP | C CÓDIGO | D DESCRIÇÃO | M DATA ENTREGA CLIENTE |
    P STATUS | Q UNIFICADO.

    Os nomes dos cabeçalhos são sempre priorizados. As posições entram apenas
    como fallback para manter compatibilidade com o relatório atual.
    """
    return {
        "ordem": _localizar_coluna(
            pmp,
            ["ORDEM DE PRODUÇÃO", "ORDEM PRODUÇÃO", "ORDEM DE FABRICAÇÃO", "OF", "OP"],
            fallback_idx=0,
        ),
        "codigo_alternativo": _localizar_coluna(
            pmp,
            ["CÓDIGO", "CODIGO", "CÓDIGO PRODUTO", "CODIGO PRODUTO", "PRODUTO"],
            fallback_idx=2,
        ),
        "descricao": _localizar_coluna(
            pmp,
            ["DESCRIÇÃO", "DESCRICAO", "DESCRIÇÃO PRODUTO", "DESCRICAO PRODUTO"],
            fallback_idx=3,
        ),
        "data_entrega": _localizar_coluna(
            pmp,
            [
                "DATA ENTREGA CLIENTE",
                "DATA DE ENTREGA CLIENTE",
                "DATA DE ENTREGA - CLIENTE",
                "DATA DE ENTREGA",
                "DATA ENTREGA",
                "DT ENTREGA",
            ],
            fallback_idx=12,
        ),
        "status": _localizar_coluna(
            pmp,
            ["STATUS", "SITUAÇÃO", "SITUACAO"],
            fallback_idx=15,
        ),
        "unificado": _localizar_coluna(
            pmp,
            ["UNIFICADO", "CÓDIGO UNIFICADO", "CODIGO UNIFICADO", "CÓD UNIFICADO", "COD UNIFICADO"],
            fallback_idx=16,
        ),
    }


def _colunas_h001(h001):
    """
    Layout atual do H001:
    F Produto | H Material | I Descricao | L Qtde_Necessaria.
    """
    return {
        "produto": _localizar_coluna(
            h001,
            ["PRODUTO", "CÓDIGO PRODUTO", "CODIGO PRODUTO", "CÓDIGO", "CODIGO"],
            fallback_idx=5,
        ),
        "material": _localizar_coluna(
            h001,
            ["MATERIAL", "CÓDIGO MATERIAL", "CODIGO MATERIAL", "COD MATERIAL"],
            fallback_idx=7,
        ),
        "descricao_material": _localizar_coluna(
            h001,
            ["DESCRICAO", "DESCRIÇÃO", "DESCRIÇÃO MATERIAL", "DESCRICAO MATERIAL"],
            fallback_idx=8,
        ),
        "quantidade": _localizar_coluna(
            h001,
            [
                "QTDE_NECESSARIA",
                "QTDE NECESSARIA",
                "QUANTIDADE NECESSÁRIA",
                "QUANTIDADE NECESSARIA",
                "QUANTIDADE",
                "QTD",
                "QTDE",
                "QUANTIDADE POR OF",
            ],
            fallback_idx=11,
        ),
    }


def _preparar_h001(h001):
    col = _colunas_h001(h001)
    dados = h001.copy()

    dados["CÓDIGO PRODUTO"] = dados.iloc[:, col["produto"]].map(_codigo)
    dados["MATERIAL"] = dados.iloc[:, col["material"]].map(_codigo)
    dados["DESCRIÇÃO MATERIAL"] = dados.iloc[:, col["descricao_material"]].map(_texto)
    dados["QUANTIDADE POR OF"] = pd.to_numeric(
        dados.iloc[:, col["quantidade"]], errors="coerce"
    ).fillna(0)

    dados = dados[
        dados["CÓDIGO PRODUTO"].ne("")
        & dados["MATERIAL"].ne("")
        & dados["QUANTIDADE POR OF"].ne(0)
    ].copy()

    if dados.empty:
        return pd.DataFrame(
            columns=[
                "CÓDIGO PRODUTO",
                "MATERIAL",
                "DESCRIÇÃO MATERIAL",
                "QUANTIDADE POR OF",
            ]
        )

    return (
        dados.groupby(["CÓDIGO PRODUTO", "MATERIAL"], as_index=False)
        .agg(
            **{
                "DESCRIÇÃO MATERIAL": (
                    "DESCRIÇÃO MATERIAL",
                    lambda x: next((v for v in x if v), ""),
                ),
                "QUANTIDADE POR OF": ("QUANTIDADE POR OF", "sum"),
            }
        )
    )


def _preparar_pmp(pmp, codigos_h001):
    col = _colunas_pmp(pmp)
    dados = pmp.copy()

    dados["STATUS"] = dados.iloc[:, col["status"]].map(_normalizar_texto)
    dados = dados[dados["STATUS"].map(_status_programado)].copy()

    dados["ORDEM DE PRODUÇÃO"] = dados.iloc[:, col["ordem"]].map(_texto)
    dados["CÓDIGO INICIAL"] = dados.iloc[:, col["codigo_alternativo"]].map(_codigo)
    dados["DESCRIÇÃO PRODUTO"] = dados.iloc[:, col["descricao"]].map(_texto)
    dados["CÓDIGO UNIFICADO"] = dados.iloc[:, col["unificado"]].map(_codigo)
    dados["DATA DE ENTREGA"] = dados.iloc[:, col["data_entrega"]].map(_data)

    dados = dados[dados["ORDEM DE PRODUÇÃO"].ne("")].copy()

    conjunto_codigos = set(codigos_h001)

    # 1) O código UNIFICADO (Q) é o vínculo preferencial.
    # 2) Se ele não localizar BOM, utiliza o código inicial da OP (C).
    # 3) Se nenhum dos dois localizar BOM, a OP permanece no relatório em uma
    #    única linha, preservando o código inicial quando ele estiver informado.
    dados["CÓDIGO PRODUTO"] = dados["CÓDIGO UNIFICADO"]
    dados["FONTE CÓDIGO"] = "UNIFICADO"

    unificado_vincula = dados["CÓDIGO UNIFICADO"].isin(conjunto_codigos)
    inicial_informado = dados["CÓDIGO INICIAL"].ne("")
    inicial_vincula = dados["CÓDIGO INICIAL"].isin(conjunto_codigos)
    usar_inicial = ~unificado_vincula & inicial_informado

    dados.loc[usar_inicial, "CÓDIGO PRODUTO"] = dados.loc[
        usar_inicial, "CÓDIGO INICIAL"
    ]
    dados.loc[usar_inicial & inicial_vincula, "FONTE CÓDIGO"] = "INICIAL"
    dados.loc[usar_inicial & ~inicial_vincula, "FONTE CÓDIGO"] = "INICIAL_SEM_BOM"

    sem_codigo = dados["CÓDIGO PRODUTO"].eq("")
    dados.loc[sem_codigo, "FONTE CÓDIGO"] = "SEM_CÓDIGO"

    return dados[
        [
            "ORDEM DE PRODUÇÃO",
            "DESCRIÇÃO PRODUTO",
            "CÓDIGO PRODUTO",
            "CÓDIGO UNIFICADO",
            "CÓDIGO INICIAL",
            "FONTE CÓDIGO",
            "DATA DE ENTREGA",
            "STATUS",
        ]
    ].copy()


def _status_encontrados_pmp(pmp):
    try:
        idx = _colunas_pmp(pmp)["status"]
        valores = pmp.iloc[:, idx].map(_normalizar_texto)
        return [x for x in valores.unique().tolist() if x][:20]
    except Exception:
        return []


def processar_tc_tp(pmp_bruto, h001_bruto):
    avisos = []
    erros = []

    bom = _preparar_h001(h001_bruto)
    codigos_h001 = set(bom["CÓDIGO PRODUTO"].unique())
    pmp = _preparar_pmp(pmp_bruto, codigos_h001)

    if len(pmp_bruto) > 0 and pmp.empty:
        status_lidos = _status_encontrados_pmp(pmp_bruto)
        detalhe = ", ".join(status_lidos) if status_lidos else "nenhum status identificado"
        erros.append(
            "Nenhuma OP com STATUS = PROGRAMADO foi encontrada no PMP. "
            f"Status identificados: {detalhe}."
        )

    if not pmp.empty and pmp["DATA DE ENTREGA"].notna().sum() == 0:
        erros.append(
            "As OPs programadas foram encontradas, porém nenhuma DATA ENTREGA CLIENTE "
            "foi reconhecida. A exportação foi bloqueada para evitar relatório sem datas."
        )

    if len(h001_bruto) > 0 and bom.empty:
        avisos.append(
            "O H001 foi lido, mas nenhuma BOM válida foi encontrada. "
            "As OPs programadas serão mantidas com uma linha e material zerado."
        )

    vinculos = pmp.merge(bom, on="CÓDIGO PRODUTO", how="left", indicator=True)

    sem_bom = vinculos.loc[
        vinculos["_merge"].eq("left_only") | vinculos["MATERIAL"].isna(),
        [
            "ORDEM DE PRODUÇÃO",
            "CÓDIGO PRODUTO",
            "DESCRIÇÃO PRODUTO",
            "CÓDIGO UNIFICADO",
            "CÓDIGO INICIAL",
            "FONTE CÓDIGO",
        ],
    ].drop_duplicates()

    base_com_bom = vinculos[vinculos["_merge"].eq("both")].copy()
    base_com_bom.drop(columns=["_merge"], inplace=True)

    base_sem_bom = vinculos[vinculos["_merge"].eq("left_only")].copy()
    if not base_sem_bom.empty:
        base_sem_bom = base_sem_bom.drop_duplicates(
            subset=["ORDEM DE PRODUÇÃO"], keep="first"
        )
        base_sem_bom["MATERIAL"] = "00000000"
        base_sem_bom["DESCRIÇÃO MATERIAL"] = ""
        base_sem_bom["QUANTIDADE POR OF"] = 0.0
        base_sem_bom.drop(columns=["_merge"], inplace=True)

    base = pd.concat(
        [base_com_bom, base_sem_bom],
        ignore_index=True,
        sort=False,
    )

    base["DATA DE NECESSIDADE"] = base["DATA DE ENTREGA"].map(
        lambda x: x - pd.Timedelta(days=30) if pd.notna(x) else pd.NaT
    )

    hoje = date.today()

    semanas_entrega = base["DATA DE ENTREGA"].map(lambda x: _semana(x, hoje))
    base["SEMANA DE ENTREGA"] = semanas_entrega.map(lambda x: x[0])
    base["PERIODO DA SEMANA DE ENTREGA"] = semanas_entrega.map(lambda x: x[1])

    base["QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"] = 0.0
    mask_entrega = base["SEMANA DE ENTREGA"].astype(str).str.match(
        r"^\d{4}-\d{2}$", na=False
    )
    entrega_unica = base.loc[
        mask_entrega,
        ["ORDEM DE PRODUÇÃO", "CÓDIGO PRODUTO", "SEMANA DE ENTREGA"],
    ].drop_duplicates()

    if not entrega_unica.empty:
        totais_entrega = (
            entrega_unica.groupby(["CÓDIGO PRODUTO", "SEMANA DE ENTREGA"])
            .size()
            .rename("QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA")
            .reset_index()
        )
        base.drop(
            columns=["QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"],
            inplace=True,
        )
        base = base.merge(
            totais_entrega,
            on=["CÓDIGO PRODUTO", "SEMANA DE ENTREGA"],
            how="left",
        )
        base["QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"] = base[
            "QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"
        ].fillna(0)

    semanas_necessidade = base["DATA DE NECESSIDADE"].map(
        lambda x: _semana(x, hoje)
    )
    base["SEMANA DE NECESSIDADE"] = semanas_necessidade.map(lambda x: x[0])
    base["PERIODO DA SEMANA DE NECESSIDADE"] = semanas_necessidade.map(
        lambda x: x[1]
    )

    base["NECESSIDADE TOTAL DA SEMANA"] = 0.0
    mask_necessidade = base["SEMANA DE NECESSIDADE"].astype(str).str.match(
        r"^\d{4}-\d{2}$", na=False
    )
    mask_material_real = base["MATERIAL"].ne("00000000")
    mask_calculo = mask_necessidade & mask_material_real

    if mask_calculo.any():
        base.loc[mask_calculo, "NECESSIDADE TOTAL DA SEMANA"] = (
            base.loc[mask_calculo]
            .groupby(["MATERIAL", "SEMANA DE NECESSIDADE"])[
                "QUANTIDADE POR OF"
            ]
            .transform("sum")
        )

    mask_sem_bom_saida = base["MATERIAL"].eq("00000000")
    base.loc[mask_sem_bom_saida, "QUANTIDADE POR OF"] = 0.0
    base.loc[mask_sem_bom_saida, "NECESSIDADE TOTAL DA SEMANA"] = 0.0

    colunas_saida = [
        "ORDEM DE PRODUÇÃO",
        "CÓDIGO PRODUTO",
        "DESCRIÇÃO PRODUTO",
        "DATA DE ENTREGA",
        "SEMANA DE ENTREGA",
        "PERIODO DA SEMANA DE ENTREGA",
        "QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA",
        "MATERIAL",
        "DESCRIÇÃO MATERIAL",
        "QUANTIDADE POR OF",
        "DATA DE NECESSIDADE",
        "SEMANA DE NECESSIDADE",
        "PERIODO DA SEMANA DE NECESSIDADE",
        "NECESSIDADE TOTAL DA SEMANA",
    ]

    for coluna in colunas_saida:
        if coluna not in base.columns:
            base[coluna] = pd.Series(dtype="object")

    base = (
        base[colunas_saida]
        .sort_values(
            ["DATA DE ENTREGA", "MATERIAL", "ORDEM DE PRODUÇÃO"],
            na_position="last",
        )
        .reset_index(drop=True)
    )

    for coluna in ["DATA DE ENTREGA", "DATA DE NECESSIDADE"]:
        base[coluna] = (
            pd.to_datetime(base[coluna], errors="coerce")
            .dt.strftime("%d/%m/%Y")
            .fillna("")
        )

    if not sem_bom.empty:
        avisos.append(
            f"{len(sem_bom)} OP(s) com STATUS = PROGRAMADO não possuem BOM no H001 "
            "e foram mantidas no relatório em uma única linha, com material e "
            "quantidades zerados."
        )

    recuperadas_inicial = pmp[pmp["FONTE CÓDIGO"].eq("INICIAL")]
    if not recuperadas_inicial.empty:
        avisos.append(
            f"{len(recuperadas_inicial)} OP(s) foram vinculadas pelo código inicial "
            "da coluna C porque o código UNIFICADO não foi localizado no H001."
        )

    inconsistencias = []
    for _, row in sem_bom.iterrows():
        inconsistencias.append(
            {
                "TIPO": "BOM NÃO ENCONTRADA",
                "ORDEM DE PRODUÇÃO": row["ORDEM DE PRODUÇÃO"],
                "CÓDIGO UNIFICADO (Q)": row["CÓDIGO UNIFICADO"],
                "CÓDIGO INICIAL (C)": row["CÓDIGO INICIAL"],
                "CÓDIGO EXIBIDO": row["CÓDIGO PRODUTO"],
                "MENSAGEM": (
                    "Nenhum vínculo de BOM foi localizado no H001. "
                    "A OP foi mantida com uma única linha e material zerado."
                ),
            }
        )

    validacao = pd.DataFrame(inconsistencias)
    if validacao.empty:
        validacao = pd.DataFrame(
            columns=[
                "TIPO",
                "ORDEM DE PRODUÇÃO",
                "CÓDIGO UNIFICADO (Q)",
                "CÓDIGO INICIAL (C)",
                "CÓDIGO EXIBIDO",
                "MENSAGEM",
            ]
        )

    metricas = {
        "linhas_pmp_brutas": len(pmp_bruto),
        "ofs_programadas": len(pmp),
        "ofs_com_bom": base_com_bom["ORDEM DE PRODUÇÃO"].nunique(),
        "linhas_bom": len(bom),
        "linhas_resultado": len(base),
        "materiais_unicos": base_com_bom["MATERIAL"].nunique(),
        "of_sem_bom": len(sem_bom),
        "of_vinculadas_por_c": len(recuperadas_inicial),
        "avisos": len(avisos),
        "erros": len(erros),
    }

    return {
        "tratado": base,
        "validacao": validacao,
        "metricas": metricas,
        "erros": erros,
        "avisos": avisos,
    }
