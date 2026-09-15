from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Any

import pandas as pd

COLUNAS_OBRIGATORIAS = [
    "Projeto",
    "Código",
    "Descrição",
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
    "Descrição",
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
    "CONDIÇÃO",
    "SEMANA DE NECESSIDADE",
    "PERIODO DA SEMANA",
    "NECESSIDADE DA SEMANA",
    "VINCULAÇÃO DA DATA",
]


def _texto(valor: Any) -> str:
    if pd.isna(valor):
        return ""
    return str(valor).strip()


def _normalizar_cabecalho(valor: Any) -> str:
    texto = _texto(valor).upper()
    texto = "".join(
        ch for ch in unicodedata.normalize("NFD", texto)
        if unicodedata.category(ch) != "Mn"
    )
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _letra_coluna(indice_zero: int) -> str:
    numero = indice_zero + 1
    letras = ""
    while numero:
        numero, resto = divmod(numero - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


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


def _primeiro_texto(grupo: pd.Series) -> str:
    for valor in grupo:
        texto = _texto(valor)
        if texto:
            return texto
    return ""


def _domingo_da_semana(data_referencia: date) -> date:
    return data_referencia - timedelta(days=(data_referencia.weekday() + 1) % 7)


def _semana_operacional(valor: Any, hoje: date) -> tuple[str, str]:
    """Calcula a semana operacional (domingo a sábado).

    A DATA MRP exibida nunca é alterada. Somente a semana é corrigida:
    datas anteriores a hoje e registros sem data são posicionados na semana atual.
    """
    if pd.isna(valor):
        data_calculo = hoje
    else:
        data_original = pd.Timestamp(valor).date()
        data_calculo = hoje if data_original < hoje else data_original

    primeiro_domingo = date(data_calculo.year, 1, 1)
    while primeiro_domingo.weekday() != 6:
        primeiro_domingo += timedelta(days=1)

    domingo = _domingo_da_semana(data_calculo)
    if domingo < primeiro_domingo:
        domingo = primeiro_domingo

    semana_numero = ((domingo - primeiro_domingo).days // 7) + 1
    sabado = domingo + timedelta(days=6)
    return f"{semana_numero:02d}", f"{domingo:%d/%m/%Y} a {sabado:%d/%m/%Y}"


def _indice_coluna_por_cabecalho(df: pd.DataFrame, termos: list[str]) -> int | None:
    cabecalhos = [_normalizar_cabecalho(c) for c in df.columns]
    termos_norm = [_normalizar_cabecalho(t) for t in termos]
    for i, cab in enumerate(cabecalhos):
        if any(cab == termo for termo in termos_norm):
            return i
    for i, cab in enumerate(cabecalhos):
        if any(len(termo) >= 4 and termo in cab for termo in termos_norm):
            return i
    return None


def _parece_condicao(valor: Any) -> bool:
    texto = _normalizar_cabecalho(valor)
    if not texto or texto == "-":
        return False
    padroes = (
        "NORMAL",
        "SUSPENS",
        "FINALIZ",
        "CANCEL",
        "ENCERR",
        "BLOQUE",
        "PARALIS",
    )
    return any(p in texto for p in padroes)


def _detectar_coluna_condicao(base: pd.DataFrame) -> int | None:
    indice = _indice_coluna_por_cabecalho(base, ["CONDIÇÃO", "CONDICAO"])
    if indice is not None:
        serie = base.iloc[:, indice].map(_texto)
        if serie.ne("").any():
            return indice

    melhor_indice = None
    melhor_pontuacao = 0
    for i in range(base.shape[1]):
        serie = base.iloc[:, i].map(_texto)
        pontuacao = int(serie.map(_parece_condicao).sum())
        if pontuacao > melhor_pontuacao:
            melhor_indice = i
            melhor_pontuacao = pontuacao

    return melhor_indice if melhor_pontuacao > 0 else indice


def _mapa_for001(for001: pd.DataFrame, avisos: list[str]):
    if for001.shape[1] < 15:
        return None, [
            "FOR-001: não há colunas suficientes para localizar OP, DATA DE ENTREGA - CLIENTE, DT MRP e CONDIÇÃO."
        ]

    base = for001.copy()

    idx_op = _indice_coluna_por_cabecalho(
        base,
        ["ORDEM PRODUÇÃO", "ORDEM PRODUCAO", "ORDEM DE PRODUÇÃO", "ORDEM DE PRODUCAO", "OP"],
    )
    if idx_op is None:
        idx_op = 0

    idx_cliente = _indice_coluna_por_cabecalho(
        base,
        ["DATA DE ENTREGA - CLIENTE", "DATA DE ENTREGA CLIENTE", "DATA ENTREGA CLIENTE"],
    )
    if idx_cliente is None:
        idx_cliente = 12 if base.shape[1] > 12 else None

    idx_mrp = _indice_coluna_por_cabecalho(base, ["DT MRP", "DATA MRP"])
    if idx_mrp is None:
        idx_mrp = 13 if base.shape[1] > 13 else None

    idx_cond = _detectar_coluna_condicao(base)
    if idx_cond is None and base.shape[1] > 14:
        idx_cond = 14

    if idx_cliente is None:
        return None, ["FOR-001: não foi possível localizar a coluna DATA DE ENTREGA - CLIENTE."]
    if idx_mrp is None:
        return None, ["FOR-001: não foi possível localizar a coluna DT MRP."]
    if idx_cond is None:
        return None, ["FOR-001: não foi possível localizar a coluna CONDIÇÃO."]

    avisos.append(
        f"FOR-001: OP lida da coluna {_letra_coluna(idx_op)}, "
        f"DATA CLIENTE da coluna {_letra_coluna(idx_cliente)}, "
        f"DT MRP da coluna {_letra_coluna(idx_mrp)} e CONDIÇÃO da coluna {_letra_coluna(idx_cond)}."
    )

    base["_OP"] = base.iloc[:, idx_op].map(_normalizar_op)
    base["_DATA_CLIENTE"] = pd.to_datetime(base.iloc[:, idx_cliente], errors="coerce", dayfirst=True)
    base["_DT_MRP"] = pd.to_datetime(base.iloc[:, idx_mrp], errors="coerce", dayfirst=True)
    base["_CONDICAO"] = base.iloc[:, idx_cond].map(_texto).str.upper()
    base = base[base["_OP"] != ""].copy()

    registros = {}
    conflitos = 0
    for _, row in base.iterrows():
        op = row["_OP"]
        data_cliente = row["_DATA_CLIENTE"]
        dt_mrp = row["_DT_MRP"]
        cond = row["_CONDICAO"]
        atual = registros.get(op)
        if atual is None:
            registros[op] = {
                "data_cliente": data_cliente,
                "data_mrp": dt_mrp,
                "condicao": cond,
            }
            continue

        if not pd.isna(data_cliente) and (
            pd.isna(atual["data_cliente"]) or data_cliente != atual["data_cliente"]
        ):
            if not pd.isna(atual["data_cliente"]):
                conflitos += 1
            atual["data_cliente"] = data_cliente

        if not pd.isna(dt_mrp) and (
            pd.isna(atual["data_mrp"]) or dt_mrp != atual["data_mrp"]
        ):
            if not pd.isna(atual["data_mrp"]):
                conflitos += 1
            atual["data_mrp"] = dt_mrp

        if cond and cond != "-" and cond != atual["condicao"]:
            if atual["condicao"] and atual["condicao"] != "-":
                conflitos += 1
            atual["condicao"] = cond

    avisos.append(f"FOR-001: {len(registros):,} OP(s) válidas carregadas para vínculo.".replace(",", "."))
    if conflitos:
        avisos.append(
            f"FOR-001: {conflitos} ocorrência(s) de OP com mais de uma DATA CLIENTE/DT MRP/CONDIÇÃO; "
            "foi mantido o último registro válido encontrado."
        )
    return registros, []


def _mapa_for022(for022: pd.DataFrame, avisos: list[str]):
    if for022.shape[1] < 22:
        return None, ["FOR-022: são necessárias pelo menos 22 colunas para acessar A e V."]
    base = for022.copy()
    base["_OP"] = base.iloc[:, 0].map(_normalizar_op)
    base["_SEPARACAO"] = pd.to_datetime(base.iloc[:, 21], errors="coerce", dayfirst=True)
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


def _chave_fallback_op(op: Any) -> str:
    texto = _normalizar_op(op)
    if len(texto) != 11 or not texto.isdigit():
        return ""
    # Quando os sistemas divergem apenas no bloco intermediário da OP,
    # usamos PSY (6 primeiros dígitos) + sequencial final (3 últimos) como chave auxiliar.
    return texto[:6] + texto[-3:]


def _resolver_fallbacks_pcp(ops: list[str], mapa001: dict, mapa022: dict) -> dict[str, str]:
    indice001: dict[str, list[str]] = {}
    indice022: dict[str, list[str]] = {}

    for candidato in mapa001.keys():
        chave = _chave_fallback_op(candidato)
        if chave:
            indice001.setdefault(chave, []).append(candidato)

    for candidato in mapa022.keys():
        chave = _chave_fallback_op(candidato)
        if chave:
            indice022.setdefault(chave, []).append(candidato)

    fallbacks: dict[str, str] = {}
    for op in ops:
        if not op or (op in mapa001 and op in mapa022):
            continue
        chave = _chave_fallback_op(op)
        if not chave:
            continue
        candidatos_comuns = sorted(set(indice001.get(chave, [])) & set(indice022.get(chave, [])))
        if len(candidatos_comuns) == 1:
            fallbacks[op] = candidatos_comuns[0]

    return fallbacks


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
        avisos.append(
            f"{duplicadas} linha(s) pertencem a {grupos_duplicados} COD_MRP duplicado(s) e foram agrupadas; "
            "nenhuma foi simplesmente excluída."
        )

    agrupado = (
        df.groupby("COD_MRP", sort=False, dropna=False)
        .agg(
            Projeto=("Projeto", "first"),
            Código=("Código", "first"),
            Descrição=("Descrição", _primeiro_texto),
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

    ops_unicas = [op for op in agrupado["_OP"].dropna().unique().tolist() if op]
    fallbacks = _resolver_fallbacks_pcp(ops_unicas, mapa001, mapa022)
    agrupado["_OP_PCP"] = agrupado["_OP"].map(lambda op: fallbacks.get(op, op))

    for op_origem, op_pcp in sorted(fallbacks.items()):
        avisos.append(
            f"Vínculo auxiliar de OP: {op_origem} não foi encontrada exatamente nos dois PCPs; "
            f"foi vinculada a {op_pcp} por PSY + sequencial final, com correspondência única em FOR-001 e FOR-022."
        )

    def resolver_data_mrp(op: str):
        if not op or op not in mapa001:
            return pd.NaT, "SEM DATA"
        registro = mapa001.get(op, {})
        data_mrp = registro.get("data_mrp", pd.NaT)
        if not pd.isna(data_mrp):
            return data_mrp, "DATA MRP"
        data_cliente = registro.get("data_cliente", pd.NaT)
        if not pd.isna(data_cliente):
            return data_cliente, "DATA CLIENTE"
        return pd.NaT, "SEM DATA"

    datas_resolvidas = agrupado["_OP_PCP"].map(resolver_data_mrp)
    agrupado["_DATA_MRP_RESOLVIDA"] = datas_resolvidas.map(lambda x: x[0])
    agrupado["VINCULAÇÃO DA DATA"] = datas_resolvidas.map(lambda x: x[1])

    agrupado["CONDIÇÃO"] = agrupado["_OP_PCP"].map(
        lambda op: mapa001.get(op, {}).get("condicao", "") if op and op in mapa001 else "NI"
    )
    agrupado["CONDIÇÃO"] = agrupado["CONDIÇÃO"].map(lambda x: _texto(x) or "NI")

    agrupado["DATA CM"] = agrupado["_OP_PCP"].map(
        lambda op: mapa022.get(op, pd.NaT) if op else pd.NaT
    )

    hoje = date.today()
    semanas = agrupado["_DATA_MRP_RESOLVIDA"].map(lambda valor: _semana_operacional(valor, hoje))
    agrupado["SEMANA DE NECESSIDADE"] = semanas.map(lambda x: x[0])
    agrupado["PERIODO DA SEMANA"] = semanas.map(lambda x: x[1])

    # Todos os produtos recebem semana. A data exibida permanece a data de origem,
    # mas uma data vencida ou ausente é enquadrada na semana atual para o cálculo do MRP.
    agrupado["NECESSIDADE DA SEMANA"] = (
        agrupado.groupby(["Código", "SEMANA DE NECESSIDADE"])["Pendência"].transform("sum")
    )

    sem_op = agrupado["_OP_PCP"].eq("") | ~agrupado["_OP_PCP"].isin(mapa001.keys())
    if sem_op.any():
        avisos.append(
            f"{int(sem_op.sum())} linha(s) do Relatório Geral não tiveram a OP identificada no FOR-001; "
            "DATA MRP = NI, CONDIÇÃO = NI e a semana foi posicionada na semana atual."
        )

    sem_data = agrupado["VINCULAÇÃO DA DATA"].eq("SEM DATA")
    if sem_data.any():
        avisos.append(
            f"{int(sem_data.sum())} linha(s) ficaram sem DATA MRP e sem DATA CLIENTE; "
            "a DATA MRP foi exibida como NI e a SEMANA DE NECESSIDADE foi posicionada na semana atual."
        )

    sem_cm = agrupado["_OP_PCP"].eq("") | ~agrupado["_OP_PCP"].isin(mapa022.keys())
    if sem_cm.any():
        avisos.append(f"{int(sem_cm.sum())} linha(s) não tiveram a OP identificada no FOR-022; DATA CM = NI.")

    agrupado["DATA MRP"] = agrupado["_DATA_MRP_RESOLVIDA"].map(
        lambda x: _data_exibicao(x) if not pd.isna(x) else "NI"
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
                "Semana atribuída": bool(re.fullmatch(r"\d{2}", str(grupo.iloc[0]["SEMANA DE NECESSIDADE"]))),
            }
        )
    validacao = pd.DataFrame(validacoes)

    invalidos = int((~validacao["Projeto válido"]).sum()) + int((~validacao["Código válido"]).sum())
    if invalidos:
        erros.append(f"{invalidos} validação(ões) de código falharam após a conversão.")

    sem_semana = int((~validacao["Semana atribuída"]).sum())
    if sem_semana:
        erros.append(f"{sem_semana} linha(s) ficaram sem semana numérica após o tratamento.")

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
