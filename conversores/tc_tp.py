import re
import unicodedata
from datetime import date, timedelta

import pandas as pd


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


def _domingo_da_semana(data_referencia):
    primeiro_domingo = date(data_referencia.year, 1, 1)
    while primeiro_domingo.weekday() != 6:
        primeiro_domingo += timedelta(days=1)
    if data_referencia < primeiro_domingo:
        return None
    return data_referencia - timedelta(days=(data_referencia.weekday() + 1) % 7)


def _semana(valor, hoje=None):
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


def _localizar_coluna(df, aliases, fallback_idx=None, valores_referencia=None):
    aliases_norm = {_normalizar_texto(x) for x in aliases}

    for idx, coluna in enumerate(df.columns):
        nome = _normalizar_texto(coluna)
        if nome in aliases_norm:
            return idx

    if valores_referencia:
        refs = {_normalizar_texto(x) for x in valores_referencia}
        limite = min(len(df), 80)
        for idx in range(df.shape[1]):
            valores = df.iloc[:limite, idx].map(_normalizar_texto)
            if valores.isin(refs).any():
                return idx

    if fallback_idx is not None and 0 <= fallback_idx < df.shape[1]:
        return fallback_idx

    return None


def _status_programado(valor):
    return _normalizar_texto(valor).startswith("PROGRAMAD")


def _colunas_pmp(pmp):
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
            ["DATA DE ENTREGA", "DT ENTREGA", "DATA ENTREGA"],
            fallback_idx=11,
        ),
        "status": _localizar_coluna(
            pmp,
            ["STATUS", "SITUAÇÃO", "SITUACAO"],
            fallback_idx=14,
            valores_referencia=["PROGRAMADO", "PROGRAMADA"],
        ),
        "unificado": _localizar_coluna(
            pmp,
            ["CÓDIGO UNIFICADO", "CODIGO UNIFICADO", "CÓD UNIFICADO", "COD UNIFICADO"],
            fallback_idx=15,
        ),
    }


def _colunas_h001(h001):
    return {
        "produto": _localizar_coluna(
            h001,
            ["CÓDIGO PRODUTO", "CODIGO PRODUTO", "PRODUTO", "CÓDIGO", "CODIGO"],
            fallback_idx=5,
        ),
        "material": _localizar_coluna(
            h001,
            ["MATERIAL", "CÓDIGO MATERIAL", "CODIGO MATERIAL", "COD MATERIAL"],
            fallback_idx=7,
        ),
        "descricao_material": _localizar_coluna(
            h001,
            ["DESCRIÇÃO MATERIAL", "DESCRICAO MATERIAL", "DESCRIÇÃO", "DESCRICAO"],
            fallback_idx=8,
        ),
        "quantidade": _localizar_coluna(
            h001,
            ["QUANTIDADE", "QTD", "QTDE", "QUANTIDADE POR OF"],
            fallback_idx=11,
        ),
    }


def _preparar_pmp(pmp, codigos_h001):
    _normalizar_colunas(
        pmp,
        {"ordem": 0, "codigo_alternativo": 2, "descricao": 3, "data_entrega": 11, "status": 14, "unificado": 15},
        "PMP_ATUALIZADO",
    )
    col = _colunas_pmp(pmp)
    dados = pmp.copy()

    dados["STATUS"] = dados.iloc[:, col["status"]].map(_normalizar_texto)
    dados = dados[dados["STATUS"].map(_status_programado)].copy()
    dados["ORDEM DE PRODUÇÃO"] = dados.iloc[:, col["ordem"]].map(_texto)
    dados["CÓDIGO ALTERNATIVO"] = dados.iloc[:, col["codigo_alternativo"]].map(_codigo)
    dados["DESCRIÇÃO PRODUTO"] = dados.iloc[:, col["descricao"]].map(_texto)
    dados["CÓDIGO UNIFICADO"] = dados.iloc[:, col["unificado"]].map(_codigo)
    dados["DATA DE ENTREGA"] = dados.iloc[:, col["data_entrega"]].map(_data)
    dados = dados[dados["ORDEM DE PRODUÇÃO"].ne("")].copy()

    conjunto_codigos = set(codigos_h001)
    dados["CÓDIGO PRODUTO"] = dados["CÓDIGO UNIFICADO"]
    dados["FONTE CÓDIGO"] = "P"

    mascara_p_vincula = dados["CÓDIGO UNIFICADO"].isin(conjunto_codigos)
    mascara_c_informado = dados["CÓDIGO ALTERNATIVO"].ne("")
    mascara_c_vincula = dados["CÓDIGO ALTERNATIVO"].isin(conjunto_codigos)
    mascara_fallback_c = ~mascara_p_vincula & mascara_c_informado

    dados.loc[mascara_fallback_c, "CÓDIGO PRODUTO"] = dados.loc[
        mascara_fallback_c, "CÓDIGO ALTERNATIVO"
    ]
    dados.loc[mascara_fallback_c & mascara_c_vincula, "FONTE CÓDIGO"] = "C"
    dados.loc[mascara_fallback_c & ~mascara_c_vincula, "FONTE CÓDIGO"] = "C_SEM_BOM"

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
    _normalizar_colunas(
        h001,
        {"produto": 5, "material": 7, "descricao_material": 8, "quantidade": 11},
        "H001",
    )
    col = _colunas_h001(h001)
    dados = h001.copy()
    dados["CÓDIGO PRODUTO"] = dados.iloc[:, col["produto"]].map(_codigo)
    dados["MATERIAL"] = dados.iloc[:, col["material"]].map(_codigo)
    dados["DESCRIÇÃO MATERIAL"] = dados.iloc[:, col["descricao_material"]].map(_texto)
    dados["QUANTIDADE POR OF"] = pd.to_numeric(dados.iloc[:, col["quantidade"]], errors="coerce").fillna(0)
    dados = dados[
        (dados["CÓDIGO PRODUTO"] != "")
        & (dados["MATERIAL"] != "")
        & (dados["QUANTIDADE POR OF"] != 0)
    ].copy()
    return (
        dados.groupby(["CÓDIGO PRODUTO", "MATERIAL"], as_index=False)
        .agg(
            **{
                "DESCRIÇÃO MATERIAL": ("DESCRIÇÃO MATERIAL", lambda x: next((v for v in x if v), "")),
                "QUANTIDADE POR OF": ("QUANTIDADE POR OF", "sum"),
            }
        )
    )


def _status_encontrados_pmp(pmp):
    try:
        idx = _colunas_pmp(pmp)["status"]
        valores = pmp.iloc[:, idx].map(_normalizar_texto)
        return [x for x in valores.unique().tolist() if x][:12]
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
        detalhe = ", ".join(status_lidos) if status_lidos else "não foi possível identificar os valores da coluna de status"
        erros.append(
            "Nenhuma OP programada foi encontrada no PMP. "
            f"Status identificados: {detalhe}. Verifique se a coluna STATUS/posição do PMP corresponde ao relatório enviado."
        )

    if len(h001_bruto) > 0 and bom.empty:
        avisos.append(
            "O H001 foi lido, mas nenhuma linha de BOM válida foi encontrada. "
            "As OPs programadas serão mantidas em uma única linha com material zerado até que exista vínculo de engenharia."
        )

    vinculos = pmp.merge(bom, on="CÓDIGO PRODUTO", how="left", indicator=True)

    sem_codigo = pmp[~pmp["CÓDIGO PRODUTO"].isin(codigos_h001)][
        ["ORDEM DE PRODUÇÃO", "DESCRIÇÃO PRODUTO", "CÓDIGO UNIFICADO", "CÓDIGO ALTERNATIVO", "CÓDIGO PRODUTO"]
    ].drop_duplicates()

    sem_bom = vinculos.loc[
        (vinculos["_merge"] == "left_only") | vinculos["MATERIAL"].isna(),
        ["ORDEM DE PRODUÇÃO", "CÓDIGO PRODUTO", "DESCRIÇÃO PRODUTO"],
    ].drop_duplicates()

    base_com_bom = vinculos[vinculos["_merge"] == "both"].copy()
    base_com_bom.drop(columns=["_merge"], inplace=True)

    base_sem_bom = vinculos[vinculos["_merge"] == "left_only"].copy()
    if not base_sem_bom.empty:
        base_sem_bom = base_sem_bom.drop_duplicates(subset=["ORDEM DE PRODUÇÃO"], keep="first")
        base_sem_bom["MATERIAL"] = "00000000"
        base_sem_bom["DESCRIÇÃO MATERIAL"] = ""
        base_sem_bom["QUANTIDADE POR OF"] = 0.0
        base_sem_bom.drop(columns=["_merge"], inplace=True)

    base = pd.concat([base_com_bom, base_sem_bom], ignore_index=True, sort=False)

    base["DATA DE NECESSIDADE"] = base["DATA DE ENTREGA"].map(
        lambda x: x - pd.Timedelta(days=30) if pd.notna(x) else pd.NaT
    )
    hoje = date.today()
    semanas_entrega = base["DATA DE ENTREGA"].map(lambda x: _semana(x, hoje))
    base["SEMANA DE ENTREGA"] = semanas_entrega.map(lambda x: x[0])
    base["PERIODO DA SEMANA DE ENTREGA"] = semanas_entrega.map(lambda x: x[1])

    base["QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"] = 0.0
    mask_entrega = base["SEMANA DE ENTREGA"].astype(str).str.match(r"^\d{2}$", na=False)
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
        base = base.merge(totais_entrega, on=["CÓDIGO PRODUTO", "SEMANA DE ENTREGA"], how="left")
        base["QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"] = base[
            "QUANTIDADE TOTAL PREVISTA ENTREGA NA SEMANA"
        ].fillna(0)

    semanas_necessidade = base["DATA DE NECESSIDADE"].map(lambda x: _semana(x, hoje))
    base["SEMANA DE NECESSIDADE"] = semanas_necessidade.map(lambda x: x[0])
    base["PERIODO DA SEMANA DE NECESSIDADE"] = semanas_necessidade.map(lambda x: x[1])

    base["NECESSIDADE TOTAL DA SEMANA"] = 0.0
    mask_necessidade = base["SEMANA DE NECESSIDADE"].astype(str).str.match(r"^\d{2}$", na=False)
    mask_material_real = base["MATERIAL"].ne("00000000")
    mask_calculo = mask_necessidade & mask_material_real
    if mask_calculo.any():
        base.loc[mask_calculo, "NECESSIDADE TOTAL DA SEMANA"] = (
            base.loc[mask_calculo]
            .groupby(["MATERIAL", "SEMANA DE NECESSIDADE"])["QUANTIDADE POR OF"]
            .transform("sum")
        )

    mask_sem_bom_saida = base["MATERIAL"].eq("00000000")
    base.loc[mask_sem_bom_saida, "QUANTIDADE POR OF"] = 0.0
    base.loc[mask_sem_bom_saida, "NECESSIDADE TOTAL DA SEMANA"] = 0.0

    colunas = [
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

    for coluna in colunas:
        if coluna not in base.columns:
            base[coluna] = pd.Series(dtype="object")

    base = base[colunas].sort_values(
        ["DATA DE ENTREGA", "MATERIAL", "ORDEM DE PRODUÇÃO"],
        na_position="last",
    ).reset_index(drop=True)

    for coluna in ["DATA DE ENTREGA", "DATA DE NECESSIDADE"]:
        base[coluna] = pd.to_datetime(base[coluna], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")

    if not sem_codigo.empty:
        avisos.append(
            f"{len(sem_codigo)} OF(s) programada(s) não conseguiram localizar o código unificado nem o código inicial no H001. O código inicial foi preservado no relatório sempre que informado."
        )
        for _, row in sem_codigo.iterrows():
            avisos.append(
                f"OF {row['ORDEM DE PRODUÇÃO']} — código P: {row['CÓDIGO UNIFICADO'] or 'NÃO INFORMADO'} — código inicial C: {row['CÓDIGO ALTERNATIVO'] or 'NÃO INFORMADO'} — código exibido: {row['CÓDIGO PRODUTO'] or 'NÃO INFORMADO'} — sem BOM no H001."
            )

    recuperadas_por_c = pmp[pmp["FONTE CÓDIGO"] == "C"]
    if not recuperadas_por_c.empty:
        avisos.append(
            f"{len(recuperadas_por_c)} OF(s) foram vinculadas pelo código inicial da coluna C porque o código da coluna P não foi localizado no H001."
        )
        for _, row in recuperadas_por_c.iterrows():
            avisos.append(
                f"OF {row['ORDEM DE PRODUÇÃO']} — código P: {row['CÓDIGO UNIFICADO'] or 'NÃO INFORMADO'} — vinculado pelo código C: {row['CÓDIGO ALTERNATIVO']}."
            )

    if not sem_bom.empty:
        avisos.append(
            f"{len(sem_bom)} OF(s) programada(s) permaneceram sem BOM e foram mantidas no relatório com uma única linha e informações de material zeradas."
        )

    inconsistencias = []
    for _, row in sem_codigo.iterrows():
        inconsistencias.append(
            {
                "TIPO": "BOM NÃO ENCONTRADA",
                "ORDEM DE PRODUÇÃO": row["ORDEM DE PRODUÇÃO"],
                "CÓDIGO UNIFICADO (P)": row["CÓDIGO UNIFICADO"],
                "CÓDIGO INICIAL (C)": row["CÓDIGO ALTERNATIVO"],
                "CÓDIGO EXIBIDO": row["CÓDIGO PRODUTO"],
                "MENSAGEM": "Nenhum dos códigos foi localizado na coluna F do H001. OF mantida no relatório com o código inicial quando disponível e material zerado.",
            }
        )
    validacao = pd.DataFrame(inconsistencias)
    if validacao.empty:
        validacao = pd.DataFrame(
            columns=[
                "TIPO", "ORDEM DE PRODUÇÃO", "CÓDIGO UNIFICADO (P)",
                "CÓDIGO INICIAL (C)", "CÓDIGO EXIBIDO", "MENSAGEM",
            ]
        )

    metricas = {
        "linhas_pmp_brutas": len(pmp_bruto),
        "ofs_programadas": len(pmp),
        "ofs_com_bom": base_com_bom["ORDEM DE PRODUÇÃO"].nunique(),
        "linhas_bom": len(bom),
        "linhas_resultado": len(base),
        "materiais_unicos": base_com_bom["MATERIAL"].nunique(),
        "of_sem_codigo": len(sem_codigo),
        "of_sem_bom": len(sem_bom),
        "of_vinculadas_por_c": len(recuperadas_por_c),
        "avisos": len(avisos),
        "erros": len(erros),
    }
    return {"tratado": base, "validacao": validacao, "metricas": metricas, "erros": erros, "avisos": avisos}
