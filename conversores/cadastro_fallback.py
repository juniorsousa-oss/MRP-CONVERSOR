"""Identificação provisória e auditável de códigos faltantes no Relatório Geral.

Apenas associa automaticamente quando existe código único e descrição
inequívoca no CADASTROS. Em caso de ambiguidade, exige correção da origem.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any

import pandas as pd


def _texto(value: Any) -> str:
    if value is None or (not isinstance(value, (list, tuple, dict)) and pd.isna(value)):
        return ""
    return str(value).strip()


def _descricao(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _texto(value).upper())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", text)).strip()


def _codigo(value: Any) -> str:
    text = _texto(value)
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text.zfill(8) if text.isdigit() and len(text) <= 8 else ""


def _numeros(descricao: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+", descricao))


def _catalogo(cadastros: pd.DataFrame) -> list[dict[str, str]]:
    # Layout oficial: linha 1 em branco; cabeçalho da linha 2 já aplicado
    # no pipeline com header=1. B = Código, C = Descrição, D = Tipo.
    if cadastros is None or cadastros.shape[1] < 4:
        raise ValueError(
            "CADASTROS indisponível ou sem as colunas B (Código), "
            "C (Descrição) e D (Tipo)."
        )
    registros: dict[tuple[str, str], dict[str, str]] = {}
    for codigo_bruto, descricao_bruta, tipo_bruto in zip(
        cadastros.iloc[:, 1], cadastros.iloc[:, 2], cadastros.iloc[:, 3]
    ):
        codigo = _codigo(codigo_bruto)
        descricao = _descricao(descricao_bruta)
        if not codigo or not descricao:
            continue
        chave = (codigo, descricao)
        if chave not in registros:
            registros[chave] = {
                "codigo": codigo,
                "descricao": _texto(descricao_bruta),
                "normalizada": descricao,
                "tipo": _texto(tipo_bruto),
            }
    if not registros:
        raise ValueError("CADASTROS não possui códigos e descrições válidos.")
    return list(registros.values())


def _classificar(
    descricao: str, catalogo: list[dict[str, str]]
) -> tuple[str, str, list[dict[str, Any]]]:
    alvo = _descricao(descricao)
    if not alvo:
        return "", "", []

    exatos = [c for c in catalogo if c["normalizada"] == alvo]
    codigos_exatos = {c["codigo"] for c in exatos}
    if len(codigos_exatos) == 1:
        candidato = exatos[0]
        return candidato["codigo"], "EXATA_UNICA", [
            {**candidato, "similaridade": 100.0} for candidato in exatos[:5]
        ]
    if len(codigos_exatos) > 1:
        # Mesmo texto cadastrado sob vários códigos: jamais escolher ao acaso.
        return "", "AMBIGUA_EXATA", [
            {**c, "similaridade": 100.0} for c in exatos[:8]
        ]

    # Para descrição curta e genérica (ex. BASCULANTE), somente igualdade
    # exata permite preenchimento automático. Demais resultados são sugestões.
    palavras = alvo.split()
    numeros_alvo = _numeros(alvo)
    proximos: list[dict[str, Any]] = []
    for item in catalogo:
        nome = item["normalizada"]
        if alvo[0] != nome[0] and not set(palavras).intersection(nome.split()):
            continue
        nota = SequenceMatcher(None, alvo, nome).ratio()
        if nota < 0.63:
            continue
        proximos.append({**item, "similaridade": round(nota * 100, 1)})
    proximos.sort(key=lambda c: (-c["similaridade"], c["codigo"]))
    sugestoes = proximos[:8]

    if len(palavras) < 2 or not sugestoes:
        return "", "SEM_CORRESPONDENCIA_UNICA", sugestoes

    primeiro = sugestoes[0]
    segundo = max(
        (c["similaridade"] for c in proximos if c["codigo"] != primeiro["codigo"]),
        default=0.0,
    )
    # Similaridade extremamente alta, distância expressiva para o segundo
    # código e especificações numéricas idênticas. Não usa simples substring.
    unico = (
        primeiro["similaridade"] >= 97.5
        and primeiro["similaridade"] - segundo >= 8.0
        and numeros_alvo == _numeros(primeiro["normalizada"])
    )
    if unico:
        return primeiro["codigo"], "SIMILAR_UNICA", sugestoes
    return "", "AMBIGUA_OU_INSUFICIENTE", sugestoes


def recuperar_codigos(
    bruto: pd.DataFrame, cadastros: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    """Retorna cópia corrigida, auditoria das substituições e candidatos.

    Não altera o CADASTROS, nem sobrescreve códigos presentes na fonte.
    Falhas ou ambiguidades continuam como código vazio e bloqueiam publicação.
    """
    df = bruto.copy()
    catalogo = _catalogo(cadastros)
    df["ORIGEM DO CÓDIGO"] = "RELATÓRIO GERAL"
    df["DESCRIÇÃO REFERÊNCIA CADASTROS"] = ""

    trilha: list[dict[str, Any]] = []
    pendencias: list[dict[str, Any]] = []
    cache: dict[str, tuple[str, str, list[dict[str, Any]]]] = {}

    for idx in df.index:
        if _texto(df.at[idx, "Código"]):
            continue
        descricao = _texto(df.at[idx, "Descrição"])
        if not descricao:
            continue
        chave = _descricao(descricao)
        if chave not in cache:
            cache[chave] = _classificar(descricao, catalogo)
        codigo, estrategia, candidatos = cache[chave]
        detalhe = {
            "Linha de origem": int(idx) + 2,
            "Projeto": _texto(df.at[idx, "Projeto"]),
            "Descrição original": descricao,
            "Situação": estrategia,
        }
        if codigo:
            df.at[idx, "Código"] = codigo
            df.at[idx, "ORIGEM DO CÓDIGO"] = "CADASTROS - PROVISÓRIO"
            referencia = next(c for c in candidatos if c["codigo"] == codigo)
            df.at[idx, "DESCRIÇÃO REFERÊNCIA CADASTROS"] = referencia["descricao"]
            trilha.append({
                **detalhe, "Código adotado": codigo,
                "Descrição CADASTROS": referencia["descricao"],
                "Similaridade (%)": referencia["similaridade"],
            })
        else:
            for c in candidatos:
                pendencias.append({
                    **detalhe, "Código candidato": c["codigo"],
                    "Descrição CADASTROS": c["descricao"],
                    "Tipo": c["tipo"],
                    "Similaridade (%)": c["similaridade"],
                })
            if not candidatos:
                pendencias.append({
                    **detalhe, "Código candidato": "",
                    "Descrição CADASTROS": "Nenhuma correspondência segura",
                    "Tipo": "", "Similaridade (%)": 0.0,
                })

    return df, trilha, pendencias
