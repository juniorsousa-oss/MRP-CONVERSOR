import pandas as pd


CC_ALVO = "600307"


def _texto(valor):
    if pd.isna(valor):
        return ""
    return str(valor).strip()


def _codigo(valor):
    if pd.isna(valor):
        return ""
    try:
        numero = int(float(valor))
        return str(numero).zfill(8)
    except (TypeError, ValueError):
        return _texto(valor)


def _data(valor):
    if pd.isna(valor) or _texto(valor) == "":
        return pd.NaT
    return pd.to_datetime(valor, errors="coerce", dayfirst=True)


def _numeros_unicos(valores):
    vistos = []
    for valor in valores:
        texto = _texto(valor)
        if texto and texto not in vistos:
            vistos.append(texto)
    return ", ".join(vistos) if vistos else "0"


def _agrupar_sc(df):
    dados = df.copy()
    dados = dados[dados.iloc[:, 8].map(_texto) == CC_ALVO].copy()
    dados["CÓD"] = dados.iloc[:, 2].map(_codigo)
    dados["DESCRIÇÃO"] = dados.iloc[:, 3].map(_texto)
    dados["DATA DA S.C"] = dados.iloc[:, 10].map(_data)
    dados["SALDO_SC"] = pd.to_numeric(dados.iloc[:, 7], errors="coerce").fillna(0)

    dados = dados[(dados["CÓD"] != "") & (dados["SALDO_SC"] > 0)].copy()

    agrupado = (
        dados.groupby(["CÓD", "DATA DA S.C"], dropna=False, as_index=False)
        .agg(
            **{
                "DESCRIÇÃO": ("DESCRIÇÃO", lambda x: next((v for v in x if v), "")),
                "S.C": (dados.columns[0], _numeros_unicos),
                "QUANTIDADE S.C": ("SALDO_SC", "sum"),
            }
        )
    )
    return agrupado


def _agrupar_pc(df):
    dados = df.copy()
    dados = dados[dados.iloc[:, 21].map(_texto) == CC_ALVO].copy()
    dados["CÓD"] = dados.iloc[:, 7].map(_codigo)
    dados["DESCRIÇÃO"] = dados.iloc[:, 9].map(_texto)
    dados["DATA DA P.C"] = dados.iloc[:, 12].map(_data)
    dados["QUANTIDADE"] = pd.to_numeric(dados.iloc[:, 13], errors="coerce").fillna(0)
    dados["QTD_ENTREGUE"] = pd.to_numeric(dados.iloc[:, 18], errors="coerce").fillna(0)
    dados["SALDO_PC"] = (dados["QUANTIDADE"] - dados["QTD_ENTREGUE"]).clip(lower=0)

    dados = dados[(dados["CÓD"] != "") & (dados["SALDO_PC"] > 0)].copy()

    agrupado = (
        dados.groupby(["CÓD", "DATA DA P.C"], dropna=False, as_index=False)
        .agg(
            **{
                "DESCRIÇÃO": ("DESCRIÇÃO", lambda x: next((v for v in x if v), "")),
                "P.C": (dados.columns[0], _numeros_unicos),
                "QUANTIDADE P.C": ("SALDO_PC", "sum"),
            }
        )
    )
    return agrupado


def _agrupar_pre_nota(df):
    dados = df.copy()
    dados["CÓD"] = dados.iloc[:, 5].map(_codigo)
    dados["DESCRIÇÃO"] = dados.iloc[:, 6].map(_texto)
    dados["QUANTIDADE"] = pd.to_numeric(dados.iloc[:, 8], errors="coerce").fillna(0)
    dados = dados[(dados["CÓD"] != "") & (dados["QUANTIDADE"] != 0)].copy()

    return (
        dados.groupby("CÓD", as_index=False)
        .agg(
            **{
                "DESCRIÇÃO": ("DESCRIÇÃO", lambda x: next((v for v in x if v), "")),
                "PRÉ-NOTA": ("QUANTIDADE", "sum"),
            }
        )
    )


def _descricao_unificada(*tabelas):
    partes = []
    for tabela in tabelas:
        if not tabela.empty:
            partes.append(tabela[["CÓD", "DESCRIÇÃO"]])
    if not partes:
        return pd.DataFrame(columns=["CÓD", "DESCRIÇÃO"])
    base = pd.concat(partes, ignore_index=True)
    base["DESCRIÇÃO"] = base["DESCRIÇÃO"].fillna("").astype(str).str.strip()
    return (
        base[base["CÓD"] != ""]
        .drop_duplicates()
        .sort_values(["CÓD", "DESCRIÇÃO"])
        .drop_duplicates("CÓD", keep="first")
        .reset_index(drop=True)
    )


def _montar_base_comum(sc, pc, pn):
    # A unidade da base é uma linha de SC ou PC por produto/data.
    # Não somamos SC com PC: são etapas diferentes do fluxo.
    linhas = []
    for _, row in sc.iterrows():
        linhas.append(
            {
                "CÓD": row["CÓD"],
                "DESCRIÇÃO": row["DESCRIÇÃO"],
                "S.C": row["S.C"],
                "QUANTIDADE S.C": row["QUANTIDADE S.C"],
                "DATA DA S.C": row["DATA DA S.C"],
                "P.C": "0",
                "QUANTIDADE P.C": 0,
                "DATA DA P.C": pd.NaT,
            }
        )
    for _, row in pc.iterrows():
        linhas.append(
            {
                "CÓD": row["CÓD"],
                "DESCRIÇÃO": row["DESCRIÇÃO"],
                "S.C": "0",
                "QUANTIDADE S.C": 0,
                "DATA DA S.C": pd.NaT,
                "P.C": row["P.C"],
                "QUANTIDADE P.C": row["QUANTIDADE P.C"],
                "DATA DA P.C": row["DATA DA P.C"],
            }
        )

    base = pd.DataFrame(linhas)
    if base.empty:
        base = pd.DataFrame(columns=[
            "CÓD", "DESCRIÇÃO", "S.C", "QUANTIDADE S.C", "DATA DA S.C",
            "P.C", "QUANTIDADE P.C", "DATA DA P.C"
        ])

    # Pré-nota é total por produto e é replicada nas linhas do produto.
    base = base.merge(pn[["CÓD", "PRÉ-NOTA"]], on="CÓD", how="left")
    base["PRÉ-NOTA"] = base["PRÉ-NOTA"].fillna(0)

    # Produtos que existem apenas na pré-nota também entram na base comum.
    existentes = set(base["CÓD"].astype(str))
    extras = pn[~pn["CÓD"].astype(str).isin(existentes)]
    if not extras.empty:
        extras = extras.copy()
        extras["S.C"] = "0"
        extras["QUANTIDADE S.C"] = 0
        extras["DATA DA S.C"] = pd.NaT
        extras["P.C"] = "0"
        extras["QUANTIDADE P.C"] = 0
        extras["DATA DA P.C"] = pd.NaT
        base = pd.concat([
            base,
            extras[["CÓD", "DESCRIÇÃO", "S.C", "QUANTIDADE S.C", "DATA DA S.C", "P.C", "QUANTIDADE P.C", "DATA DA P.C", "PRÉ-NOTA"]]
        ], ignore_index=True)

    colunas = [
        "CÓD", "DESCRIÇÃO", "S.C", "QUANTIDADE S.C", "DATA DA S.C",
        "P.C", "QUANTIDADE P.C", "DATA DA P.C", "PRÉ-NOTA"
    ]
    return base[colunas].sort_values(["CÓD", "DATA DA S.C", "DATA DA P.C"], na_position="last").reset_index(drop=True)


def processar_compras(sc_bruto, pc_bruto, pre_nota_bruto):
    sc = _agrupar_sc(sc_bruto)
    pc = _agrupar_pc(pc_bruto)
    pn = _agrupar_pre_nota(pre_nota_bruto)

    base = _montar_base_comum(sc, pc, pn)

    descricao = _descricao_unificada(sc, pc, pn)
    inconsistencias = []

    for codigo, grupo in descricao.groupby("CÓD"):
        descricoes = sorted({str(x).strip() for x in grupo["DESCRIÇÃO"] if str(x).strip()})
        if len(descricoes) > 1:
            inconsistencias.append(
                f"Produto {codigo} possui descrições diferentes entre os relatórios: " + " | ".join(descricoes)
            )

    validacao = pd.DataFrame(
        [{"TIPO": "INFO", "MENSAGEM": "Filtro aplicado: Centro de Custo = 600307 nos relatórios S.C e P.C."},
         {"TIPO": "INFO", "MENSAGEM": "S.C utiliza Saldo SC; P.C utiliza Quantidade - Qtd.Entregue; Pré-nota é somada por produto."}]
        + [{"TIPO": "INCONSISTÊNCIA", "MENSAGEM": x} for x in inconsistencias]
    )

    metricas = {
        "linhas_sc_brutas": len(sc_bruto),
        "linhas_sc_tratadas": len(sc),
        "linhas_pc_brutas": len(pc_bruto),
        "linhas_pc_tratadas": len(pc),
        "produtos_pre_nota": pn["CÓD"].nunique(),
        "linhas_base": len(base),
        "inconsistencias": len(inconsistencias),
        "erros": 0,
    }
    return {"tratado": base, "validacao": validacao, "metricas": metricas, "erros": [], "avisos": inconsistencias}
