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


def _semana_necessidade(valor, hoje=None):
    """Calcula semana domingo-sábado sem alterar a data original."""
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


def _normalizar_colunas(df, nomes_esperados, nome_arquivo):
    if df.shape[1] < max(nomes_esperados.values()) + 1:
        raise ValueError(
            f"{nome_arquivo}: quantidade de colunas insuficiente. "
            f"Esperadas pelo menos {max(nomes_esperados.values()) + 1} colunas."
        )


def _preparar_pmp(pmp):
    # PMP: A=Ordem, D=Descrição, L=Data Entrega, O=Status, P=Código Unificado.
    _normalizar_colunas(
        pmp,
        {"ordem": 0, "descricao": 3, "data_entrega": 11, "status": 14, "unificado": 15},
        "PMP_ATUALIZADO",
    )

    dados = pmp.copy()
    dados["STATUS"] = dados.iloc[:, 14].map(_texto).str.upper()
    # Pré-limpeza: somente OFs em aberto/programadas.
    dados = dados[dados["STATUS"] == "PROGRAMADO"].copy()

    dados["ORDEM DE PRODUÇÃO"] = dados.iloc[:, 0].map(_texto)
    dados["DESCRIÇÃO PRODUTO"] = dados.iloc[:, 3].map(_texto)
    dados["CÓDIGO PRODUTO"] = dados.iloc[:, 15].map(_codigo)
    dados["DATA DE ENTREGA"] = dados.iloc[:, 11].map(_data)
    dados["QUANTIDADE OF"] = 1.0

    return dados[
        [
            "ORDEM DE PRODUÇÃO",
            "DESCRIÇÃO PRODUTO",
            "CÓDIGO PRODUTO",
            "DATA DE ENTREGA",
            "QUANTIDADE OF",
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
    dados["QUANTIDADE POR OF"] = pd.to_numeric(
        dados.iloc[:, 11], errors="coerce"
    ).fillna(0)

    dados = dados[
        (dados["CÓDIGO PRODUTO"] != "")
        & (dados["MATERIAL"] != "")
        & (dados["QUANTIDADE POR OF"] != 0)
    ].copy()

    # A lista de material é fixa por produto. Caso exista repetição
    # do mesmo material no cadastro, consolidamos a quantidade.
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
    pmp = _preparar_pmp(pmp_bruto)
    bom = _preparar_h001(h001_bruto)

    # Cada OF programada representa 1 unidade do produto intermediário.
    # Para cada OF, expande-se a BOM fixa correspondente.
    base = pmp.merge(
        bom,
        on="CÓDIGO PRODUTO",
        how="left",
        indicator=True,
    )

    sem_bom = base.loc[
        (base["_merge"] == "left_only") | base["MATERIAL"].isna(),
        ["ORDEM DE PRODUÇÃO", "CÓDIGO PRODUTO", "DESCRIÇÃO PRODUTO"],
    ].drop_duplicates()

    # OFs sem código unificado não conseguem fazer a junção com H001.
    sem_codigo = pmp[pmp["CÓDIGO PRODUTO"] == ""][
        ["ORDEM DE PRODUÇÃO", "DESCRIÇÃO PRODUTO"]
    ].drop_duplicates()

    base = base[base["_merge"] == "both"].copy()
    base.drop(columns=["_merge"], inplace=True)

    base["DATA DE NECESSIDADE"] = base["DATA DE ENTREGA"].map(
        lambda x: x - pd.Timedelta(days=30) if pd.notna(x) else pd.NaT
    )

    hoje = date.today()
    semanas = base["DATA DE NECESSIDADE"].map(
        lambda x: _semana_necessidade(x, hoje)
    )
    base["SEMANA DE NECESSIDADE"] = semanas.map(lambda x: x[0])
    base["PERIODO DA SEMANA"] = semanas.map(lambda x: x[1])

    base["NECESSIDADE"] = (
        base["QUANTIDADE POR OF"] * base["QUANTIDADE OF"]
    )

    mask_semana = base["SEMANA DE NECESSIDADE"].str.match(
        r"^\d{2}$", na=False
    )
    base["NECESSIDADE DA SEMANA"] = 0.0
    if mask_semana.any():
        base.loc[mask_semana, "NECESSIDADE DA SEMANA"] = (
            base.loc[mask_semana]
            .groupby(["MATERIAL", "SEMANA DE NECESSIDADE"])["NECESSIDADE"]
            .transform("sum")
        )

    colunas = [
        "ORDEM DE PRODUÇÃO",
        "CÓDIGO PRODUTO",
        "DESCRIÇÃO PRODUTO",
        "QUANTIDADE OF",
        "DATA DE ENTREGA",
        "DATA DE NECESSIDADE",
        "MATERIAL",
        "DESCRIÇÃO MATERIAL",
        "QUANTIDADE POR OF",
        "NECESSIDADE",
        "SEMANA DE NECESSIDADE",
        "PERIODO DA SEMANA",
        "NECESSIDADE DA SEMANA",
    ]
    base = base[colunas].sort_values(
        ["DATA DE NECESSIDADE", "MATERIAL", "ORDEM DE PRODUÇÃO"],
        na_position="last",
    ).reset_index(drop=True)

    for coluna in ["DATA DE ENTREGA", "DATA DE NECESSIDADE"]:
        base[coluna] = pd.to_datetime(
            base[coluna], errors="coerce"
        ).dt.strftime("%d/%m/%Y").fillna("")

    avisos = []
    if not sem_codigo.empty:
        avisos.append(
            f"{len(sem_codigo)} OF(s) programada(s) estão sem CÓDIGO UNIFICADO na coluna P do PMP."
        )

    inconsistencias = []
    if not sem_codigo.empty:
        for _, row in sem_codigo.iterrows():
            inconsistencias.append(
                {
                    "TIPO": "SEM CÓDIGO UNIFICADO",
                    "ORDEM DE PRODUÇÃO": row["ORDEM DE PRODUÇÃO"],
                    "CÓDIGO PRODUTO": "",
                    "MENSAGEM": "Coluna P do PMP sem código para junção com H001.",
                }
            )
    if not sem_bom.empty:
        for _, row in sem_bom.iterrows():
            if row["CÓDIGO PRODUTO"] != "":
                inconsistencias.append(
                    {
                        "TIPO": "BOM NÃO ENCONTRADA",
                        "ORDEM DE PRODUÇÃO": row["ORDEM DE PRODUÇÃO"],
                        "CÓDIGO PRODUTO": row["CÓDIGO PRODUTO"],
                        "MENSAGEM": "Código do PMP não localizado na coluna F do H001.",
                    }
                )

    if not sem_bom.empty:
        codigos_sem_bom = sorted(
            set(
                sem_bom["CÓDIGO PRODUTO"]
                .astype(str)
                .str.strip()
                .replace("", pd.NA)
                .dropna()
            )
        )
        if codigos_sem_bom:
            avisos.append(
                f"{len(sem_bom)} OF(s) programada(s) não encontraram BOM no H001. "
                f"Códigos: {', '.join(codigos_sem_bom)}."
            )

    validacao = pd.DataFrame(inconsistencias)
    if validacao.empty:
        validacao = pd.DataFrame(
            columns=[
                "TIPO",
                "ORDEM DE PRODUÇÃO",
                "CÓDIGO PRODUTO",
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
        "avisos": len(avisos),
    }

    return {
        "tratado": base,
        "validacao": validacao,
        "metricas": metricas,
        "erros": [],
        "avisos": avisos,
    }
