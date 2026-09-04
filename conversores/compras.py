import pandas as pd

CC_ALVO = "600307"


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


def _numeros_unicos(valores):
    vistos = []
    for valor in valores:
        texto = _texto(valor)
        if texto and texto not in vistos:
            vistos.append(texto)
    return ", ".join(vistos) if vistos else "0"


def _formatar_datas(base):
    """Converte as datas de saída para o padrão brasileiro dd/mm/aaaa."""
    for coluna in ["DATA DA S.C", "DATA DA P.C"]:
        if coluna in base.columns:
            base[coluna] = pd.to_datetime(base[coluna], errors="coerce").dt.strftime("%d/%m/%Y")
            base[coluna] = base[coluna].fillna("")
    return base


def _agrupar_sc(df):
    dados = df.copy()
    # A = Numero SC, C = Produto, D = Descricao, G = Quantidade,
    # I = Centro Custo, K = Entrega SC, N = Saldo SC.
    dados = dados[dados.iloc[:, 8].map(_texto) == CC_ALVO].copy()
    dados["CÓD"] = dados.iloc[:, 2].map(_codigo)
    dados["DESCRIÇÃO"] = dados.iloc[:, 3].map(_texto)
    dados["DATA DA S.C"] = dados.iloc[:, 10].map(_data)
    dados["SALDO_SC"] = pd.to_numeric(dados.iloc[:, 13], errors="coerce").fillna(0)
    dados = dados[(dados["CÓD"] != "") & (dados["SALDO_SC"] > 0)].copy()

    return (
        dados.groupby(["CÓD", "DATA DA S.C"], dropna=False, as_index=False)
        .agg(
            **{
                "DESCRIÇÃO": ("DESCRIÇÃO", lambda x: next((v for v in x if v), "")),
                "S.C": (dados.columns[0], _numeros_unicos),
                "QUANTIDADE S.C": ("SALDO_SC", "sum"),
            }
        )
    )


def _agrupar_pc(df):
    dados = df.copy()
    # A = Num.PC, H = Produto, J = Descricao, M = Entrega,
    # N = Quantidade, S = Qtd.Entregue, V = Centro Custo.
    dados = dados[dados.iloc[:, 21].map(_texto) == CC_ALVO].copy()
    dados["CÓD"] = dados.iloc[:, 7].map(_codigo)
    dados["DESCRIÇÃO"] = dados.iloc[:, 9].map(_texto)
    dados["DATA DA P.C"] = dados.iloc[:, 12].map(_data)
    dados["QUANTIDADE"] = pd.to_numeric(dados.iloc[:, 13], errors="coerce").fillna(0)
    dados["QTD_ENTREGUE"] = pd.to_numeric(dados.iloc[:, 18], errors="coerce").fillna(0)
    dados["SALDO_PC"] = (dados["QUANTIDADE"] - dados["QTD_ENTREGUE"]).clip(lower=0)
    dados = dados[(dados["CÓD"] != "") & (dados["SALDO_PC"] > 0)].copy()

    return (
        dados.groupby(["CÓD", "DATA DA P.C"], dropna=False, as_index=False)
        .agg(
            **{
                "DESCRIÇÃO": ("DESCRIÇÃO", lambda x: next((v for v in x if v), "")),
                "P.C": (dados.columns[0], _numeros_unicos),
                "QUANTIDADE P.C": ("SALDO_PC", "sum"),
            }
        )
    )


def _agrupar_pre_nota(df):
    # F = Produto, G = Descricao, I = Quantidade.
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


def _montar_base_comum(sc, pc, pn):
    # Cada linha representa uma ocorrência de SC ou PC por produto/data.
    # As quantidades de SC e PC nunca são somadas entre si.
    linhas = []
    for _, row in sc.iterrows():
        linhas.append({
            "CÓD": row["CÓD"], "DESCRIÇÃO": row["DESCRIÇÃO"],
            "S.C": row["S.C"], "QUANTIDADE S.C": row["QUANTIDADE S.C"],
            "DATA DA S.C": row["DATA DA S.C"], "P.C": "0",
            "QUANTIDADE P.C": 0, "DATA DA P.C": pd.NaT,
        })
    for _, row in pc.iterrows():
        linhas.append({
            "CÓD": row["CÓD"], "DESCRIÇÃO": row["DESCRIÇÃO"],
            "S.C": "0", "QUANTIDADE S.C": 0, "DATA DA S.C": pd.NaT,
            "P.C": row["P.C"], "QUANTIDADE P.C": row["QUANTIDADE P.C"],
            "DATA DA P.C": row["DATA DA P.C"],
        })

    base = pd.DataFrame(linhas)
    if base.empty:
        base = pd.DataFrame(columns=[
            "CÓD", "DESCRIÇÃO", "S.C", "QUANTIDADE S.C", "DATA DA S.C",
            "P.C", "QUANTIDADE P.C", "DATA DA P.C"
        ])

    base = base.merge(pn[["CÓD", "PRÉ-NOTA"]], on="CÓD", how="left")
    base["PRÉ-NOTA"] = base["PRÉ-NOTA"].fillna(0)

    existentes = set(base["CÓD"].astype(str))
    extras = pn[~pn["CÓD"].astype(str).isin(existentes)].copy()
    if not extras.empty:
        extras["S.C"] = "0"; extras["QUANTIDADE S.C"] = 0; extras["DATA DA S.C"] = pd.NaT
        extras["P.C"] = "0"; extras["QUANTIDADE P.C"] = 0; extras["DATA DA P.C"] = pd.NaT
        base = pd.concat([base, extras[[
            "CÓD", "DESCRIÇÃO", "S.C", "QUANTIDADE S.C", "DATA DA S.C",
            "P.C", "QUANTIDADE P.C", "DATA DA P.C", "PRÉ-NOTA"
        ]]], ignore_index=True)

    colunas = [
        "CÓD", "DESCRIÇÃO", "S.C", "QUANTIDADE S.C", "DATA DA S.C",
        "P.C", "QUANTIDADE P.C", "DATA DA P.C", "PRÉ-NOTA"
    ]
    base = base[colunas].sort_values(
        ["CÓD", "DATA DA S.C", "DATA DA P.C"], na_position="last"
    ).reset_index(drop=True)

    # A saída do conversor deve mostrar somente a data, sem horário.
    base = _formatar_datas(base)
    return base


def processar_compras(sc_bruto, pc_bruto, pre_nota_bruto):
    sc = _agrupar_sc(sc_bruto)
    pc = _agrupar_pc(pc_bruto)
    pn = _agrupar_pre_nota(pre_nota_bruto)
    base = _montar_base_comum(sc, pc, pn)

    # Validações básicas de estrutura e descrição.
    inconsistencias = []
    todas = pd.concat([
        sc[["CÓD", "DESCRIÇÃO"]],
        pc[["CÓD", "DESCRIÇÃO"]],
        pn[["CÓD", "DESCRIÇÃO"]],
    ], ignore_index=True)
    for codigo, grupo in todas.groupby("CÓD"):
        descricoes = sorted({x for x in grupo["DESCRIÇÃO"].map(_texto) if x})
        if len(descricoes) > 1:
            inconsistencias.append(
                f"Produto {codigo} possui descrições diferentes entre os relatórios: "
                + " | ".join(descricoes)
            )

    validacao = pd.DataFrame([
        {"TIPO": "INFO", "MENSAGEM": "Filtro: Centro de Custo = 600307 em S.C e P.C."},
        {"TIPO": "INFO", "MENSAGEM": "S.C: Saldo SC. P.C: Quantidade - Qtd.Entregue. Pré-nota: soma por produto."},
        {"TIPO": "INFO", "MENSAGEM": f"S.C após filtro/abertos: {len(sc)} linhas agrupadas."},
        {"TIPO": "INFO", "MENSAGEM": f"P.C após filtro/saldo positivo: {len(pc)} linhas agrupadas."},
    ] + [
        {"TIPO": "INCONSISTÊNCIA", "MENSAGEM": x} for x in inconsistencias
    ])

    metricas = {
        "linhas_sc_brutas": len(sc_bruto), "linhas_sc_tratadas": len(sc),
        "linhas_pc_brutas": len(pc_bruto), "linhas_pc_tratadas": len(pc),
        "produtos_pre_nota": pn["CÓD"].nunique(), "linhas_base": len(base),
        "inconsistencias": len(inconsistencias), "erros": 0,
    }
    return {
        "tratado": base, "validacao": validacao, "metricas": metricas,
        "erros": [], "avisos": inconsistencias,
    }
