import pandas as pd
from datetime import date, timedelta


def _texto(valor):
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


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


def _domingo_da_semana(data_referencia):
    primeiro_domingo = date(data_referencia.year, 1, 1)
    while primeiro_domingo.weekday() != 6:
        primeiro_domingo += timedelta(days=1)
    if data_referencia < primeiro_domingo:
        return None
    return data_referencia - timedelta(days=(data_referencia.weekday() + 1) % 7)


def _semana(valor, hoje=None):
    """Calcula semana domingo-sábado. Mantém a data original intacta."""
    if hoje is None:
        hoje = date.today()
    if pd.isna(valor) or _texto(valor) == "":
        return "", ""

    data_original = pd.Timestamp(valor).date()
    data_calculo = hoje if data_original < hoje else data_original
    domingo = _domingo_da_semana(data_calculo)
    if domingo is None:
        return "", ""

    primeiro_domingo = date(data_calculo.year, 1, 1)
    while primeiro_domingo.weekday() != 6:
        primeiro_domingo += timedelta(days=1)

    numero = ((domingo - primeiro_domingo).days // 7) + 1
    sabado = domingo + timedelta(days=6)
    return f"{numero:02d}", f"{domingo:%d/%m/%Y} a {sabado:%d/%m/%Y}"


def _normalizar_colunas(df, colunas_esperadas, nome_arquivo):
    if df.shape[1] < max(colunas_esperadas.values()) + 1:
        raise ValueError(
            f"{nome_arquivo}: quantidade de colunas insuficiente. "
            f"Esperadas pelo menos {max(colunas_esperadas.values()) + 1} colunas."
        )


def _preparar_pmp(pmp, codigos_h001):
    # PMP: A=Ordem, C=Código alternativo, D=Descrição, L=Data Entrega,
    # O=Status, P=Código Unificado.
    _normalizar_colunas(
        pmp,
        {"ordem": 0, "codigo_alternativo": 2, "descricao": 3, "data_entrega": 11, "status": 14, "unificado": 15},
        "PMP_ATUALIZADO",
    )

    dados = pmp.copy()
    dados["STATUS"] = dados.iloc[:, 14].map(_texto).str.upper()
    dados = dados[dados["STATUS"] == "PROGRAMADO"].copy()

    dados["ORDEM DE PRODUÇÃO"] = dados.iloc[:, 0].map(_texto)
    dados["CÓDIGO ALTERNATIVO"] = dados.iloc[:, 2].map(_codigo)
    dados["DESCRIÇÃO PRODUTO"] = dados.iloc[:, 3].map(_texto)
    dados["CÓDIGO UNIFICADO"] = dados.iloc[:, 15].map(_codigo)
    dados["DATA DE ENTREGA"] = dados.iloc[:, 11].map(_data)

    # P é a primeira tentativa. Se P não existir no H001, tenta C.
    conjunto_codigos = set(codigos_h001)
    dados["CÓDIGO PRODUTO"] = dados["CÓDIGO UNIFICADO"]
    dados["FONTE CÓDIGO"] = "P"

    mascara_fallback = ~dados["CÓDIGO UNIFICADO"].isin(conjunto_codigos)
    mascara_c_valido = dados["CÓDIGO ALTERNATIVO"].isin(conjunto_codigos)
    dados.loc[mascara_fallback & mascara_c_valido, "CÓDIGO PRODUTO"] = dados.loc[
        mascara_fallback & mascara_c_valido, "CÓDIGO ALTERNATIVO"
    ]
    dados.loc[mascara_fallback & mascara_c_valido, "FONTE CÓDIGO"] = "C"

    return dados[
        [
            "ORDEM DE PRODUÇÃO",
            "DESCRIÇÃO PRODUTO",
            "CÓDIGO PRODUTO",
            "CÓDIGO UNIFICADO",
            "CÓDIGO ALTERNATIVO",
            "FONTE CÓDIGO",
            "DATA DE ENTREGA",
        ]
    ].copy()


def _preparar_h001(h001):
    # H001: F=Cód Produto, H=Material, I=Descrição Material, L=Qtde.
    _normalizar_colunas(
        h001,
        {"produto": 5, "material": 7, "descricao_material": 8, "quantidade": 11},
        "H001",
    )

    dados = h001.copy()
    dados["CÓDIGO PRODUTO"] = dados.iloc[:, 5].map(_codigo)
    dados["MATERIAL"] = dados.iloc[:, 7].map(_codigo)
    dados["DESCRIÇÃO MATERIAL"] = dados.iloc[:, 8].map(_texto)
    dados["QUANTIDADE POR OF"] = pd.to_numeric(dados.iloc[:, 11], errors="coerce").fillna(0)

    dados = dados[
        (dados["CÓDIGO PRODUTO"] != "")
        & (dados["MATERIAL"] != "")
        & (dados["QUANTIDADE POR OF"] != 0)
    ].copy()

    dados = (
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
    return dados


def processar_tc_tp(pmp_bruto, h001_bruto):
    bom = _preparar_h001(h001_bruto)
    codigos_h001 = set(bom["CÓDIGO PRODUTO"].unique())
    pmp = _preparar_pmp(pmp_bruto, codigos_h001)

    base = pmp.merge(bom, on="CÓDIGO PRODUTO", how="left", indicator=True)

    sem_codigo = pmp[
        ~pmp["CÓDIGO PRODUTO"].isin(codigos_h001)
    ][
        ["ORDEM DE PRODUÇÃO", "DESCRIÇÃO PRODUTO", "CÓDIGO UNIFICADO", "CÓDIGO ALTERNATIVO"]
    ].drop_duplicates()

    sem_bom = base.loc[
        (base["_merge"] == "left_only") | base["MATERIAL"].isna(),
        ["ORDEM DE PRODUÇÃO", "CÓDIGO PRODUTO", "DESCRIÇÃO PRODUTO"],
    ].drop_duplicates()

    base = base[base["_merge"] == "both"].copy()
    base.drop(columns=["_merge"], inplace=True)

    # Cada OF programada representa 1 unidade do produto intermediário.
    # A quantidade da BOM é a necessidade do componente por OF.
    base["DATA DE NECESSIDADE"] = base["DATA DE ENTREGA"].map(
        lambda x: x - pd.Timedelta(days=30) if pd.notna(x) else pd.NaT
    )

    hoje = date.today()

    # Planejamento de entrega do produto intermediário.
    semanas_entrega = base["DATA DE ENTREGA"].map(lambda x: _semana(x, hoje))
    base["SEMANA DE ENTREGA"] = semanas_entrega.map(lambda x: x[0])
    base["PERIODO DA SEMANA DE ENTREGA"] = semanas_entrega.map(lambda x: x[1])

    # A quantidade total prevista de entrega é calculada por produto + semana,
    # contando cada OF uma única vez, antes da expansão da BOM.
    base["QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"] = 0.0
    mask_entrega = base["SEMANA DE ENTREGA"].str.match(r"^\d{2}$", na=False)
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
        base = base.drop(columns=["QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"])
        base = base.merge(
            totais_entrega,
            on=["CÓDIGO PRODUTO", "SEMANA DE ENTREGA"],
            how="left",
        )
        base["QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"] = base[
            "QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"
        ].fillna(0)

    # Semana de necessidade dos componentes: data de entrega menos 30 dias.
    semanas_necessidade = base["DATA DE NECESSIDADE"].map(lambda x: _semana(x, hoje))
    base["SEMANA DE NECESSIDADE"] = semanas_necessidade.map(lambda x: x[0])
    base["PERIODO DA SEMANA DE NECESSIDADE"] = semanas_necessidade.map(lambda x: x[1])

    # Necessidade total do material na semana = soma das quantidades da BOM
    # para todas as OFs que demandam aquele material naquela semana.
    base["NECESSIDADE TOTAL DA SEMANA"] = 0.0
    mask_necessidade = base["SEMANA DE NECESSIDADE"].str.match(r"^\d{2}$", na=False)
    if mask_necessidade.any():
        base.loc[mask_necessidade, "NECESSIDADE TOTAL DA SEMANA"] = (
            base.loc[mask_necessidade]
            .groupby(["MATERIAL", "SEMANA DE NECESSIDADE"])["QUANTIDADE POR OF"]
            .transform("sum")
        )

    # Layout: após a quantidade total prevista de entrega, manter a sequência
    # da imagem de referência e deixar a necessidade total semanal por último.
    colunas = [
        "ORDEM DE PRODUÇÃO",
        "CÓDIGO PRODUTO",
        "DESCRIÇÃO PRODUTO",
        "DATA DE ENTREGA",
        "SEMANA DE ENTREGA",
        "PERIODO DA SEMANA DE ENTREGA",
        "QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA",
        "DATA DE NECESSIDADE",
        "SEMANA DE NECESSIDADE",
        "PERIODO DA SEMANA DE NECESSIDADE",
        "MATERIAL",
        "DESCRIÇÃO MATERIAL",
        "QUANTIDADE POR OF",
        "NECESSIDADE TOTAL DA SEMANA",
    ]
    base = base[colunas].sort_values(
        ["DATA DE ENTREGA", "MATERIAL", "ORDEM DE PRODUÇÃO"],
        na_position="last",
    ).reset_index(drop=True)

    for coluna in ["DATA DE ENTREGA", "DATA DE NECESSIDADE"]:
        base[coluna] = pd.to_datetime(base[coluna], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")

    avisos = []
    if not sem_codigo.empty:
        avisos.append(
            f"{len(sem_codigo)} OF(s) programada(s) não conseguiram localizar o código da coluna P nem o código alternativo da coluna C no H001."
        )
        for _, row in sem_codigo.iterrows():
            avisos.append(
                f"OF {row['ORDEM DE PRODUÇÃO']} — código P: {row['CÓDIGO UNIFICADO'] or 'NÃO INFORMADO'} — código C: {row['CÓDIGO ALTERNATIVO'] or 'NÃO INFORMADO'} — nenhum dos dois foi localizado no H001."
            )

    recuperadas_por_c = pmp[pmp["FONTE CÓDIGO"] == "C"]
    if not recuperadas_por_c.empty:
        avisos.append(
            f"{len(recuperadas_por_c)} OF(s) foram vinculadas pelo código da coluna C porque o código da coluna P não foi localizado no H001."
        )
        for _, row in recuperadas_por_c.iterrows():
            avisos.append(
                f"OF {row['ORDEM DE PRODUÇÃO']} — código P: {row['CÓDIGO UNIFICADO'] or 'NÃO INFORMADO'} — vinculado pelo código C: {row['CÓDIGO ALTERNATIVO']}."
            )

    if not sem_bom.empty:
        avisos.append(
            f"{len(sem_bom)} OF(s) programada(s) permaneceram sem BOM após as duas tentativas de vínculo."
        )

    inconsistencias = []
    for _, row in sem_codigo.iterrows():
        inconsistencias.append(
            {
                "TIPO": "BOM NÃO ENCONTRADA",
                "ORDEM DE PRODUÇÃO": row["ORDEM DE PRODUÇÃO"],
                "CÓDIGO UNIFICADO (P)": row["CÓDIGO UNIFICADO"],
                "CÓDIGO ALTERNATIVO (C)": row["CÓDIGO ALTERNATIVO"],
                "MENSAGEM": "Nenhum dos dois códigos foi localizado na coluna F do H001.",
            }
        )

    validacao = pd.DataFrame(inconsistencias)
    if validacao.empty:
        validacao = pd.DataFrame(
            columns=[
                "TIPO",
                "ORDEM DE PRODUÇÃO",
                "CÓDIGO UNIFICADO (P)",
                "CÓDIGO ALTERNATIVO (C)",
                "MENSAGEM",
            ]
        )

    metricas = {
        "linhas_pmp_brutas": len(pmp_bruto),
        "ofs_programadas": len(pmp),
        "ofs_com_bom": base["ORDEM DE PRODUÇÃO"].nunique(),
        "linhas_bom": len(bom),
        "linhas_resultado": len(base),
        "materiais_unicos": base["MATERIAL"].nunique(),
        "of_sem_codigo": len(sem_codigo),
        "of_sem_bom": len(sem_bom),
        "of_vinculadas_por_c": len(recuperadas_por_c),
        "avisos": len(avisos),
    }

    return {
        "tratado": base,
        "validacao": validacao,
        "metricas": metricas,
        "erros": [],
        "avisos": avisos,
    }
