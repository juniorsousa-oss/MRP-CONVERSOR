"""Testes offline: reprocessamento por nova semana sem alterar fontes.

Nenhum teste realiza chamadas à API da Central SETTA.
"""
from __future__ import annotations

from datetime import date
from unittest import TestCase
from unittest.mock import patch

import pandas as pd

import pipeline_sync as pipelines
from conversores import compras
from conversores.semanas import semana_operacional, versao_semana_operacional


class ReprocessamentoSemanalTests(TestCase):
    def _state(self, relatorio: str, semana: int, versoes_publicadas: dict | None = None):
        cfg = pipelines.PIPELINES[relatorio]
        fontes = {key: {"source_key": key, "available": True} for key in cfg["sources"]}
        versoes = {key: 10 for key in cfg["sources"]}
        base = {"available": True, "source_versions": versoes_publicadas or {}}
        with (
            patch.object(pipelines.central, "pipeline_state", return_value=(fontes, base)),
            patch.object(pipelines.central, "source_versions", return_value=versoes),
            patch.object(pipelines.central, "all_sources_available", return_value=True),
            patch.object(pipelines, "versao_semana_operacional", return_value=semana),
        ):
            return pipelines.get_state(relatorio)

    def test_tres_processos_utilizam_semana_operacional(self):
        for nome in ("Relatório Geral", "Compras — S.C + P.C + Pré-nota", "MRP — TC/TP"):
            with self.subTest(relatorio=nome):
                antes = self._state(nome, 20261011)
                self.assertEqual(antes["versions"]["semana_operacional_inicio"], 20261011)
                mesmo = self._state(nome, 20261011, antes["versions"])
                self.assertFalse(mesmo["stale"])
                domingo = self._state(nome, 20261018, antes["versions"])
                self.assertTrue(domingo["stale"])
                self.assertTrue(domingo["ready"])

    def test_estoque_so_reprocessa_se_fontes_mudarem(self):
        antes = self._state("Saldo em Estoque", 20261011)
        self.assertNotIn("semana_operacional_inicio", antes["versions"])
        depois = self._state("Saldo em Estoque", 20261018, antes["versions"])
        self.assertFalse(depois["stale"])

    def test_semana_usa_brasilia_sem_hoje_explicito(self):
        with patch("conversores.semanas.hoje_setta", return_value=date(2026, 10, 18)):
            self.assertEqual(semana_operacional("08/10/2026")[0], "2026-42")
        with patch("conversores.semanas.hoje_setta", return_value=date(2026, 10, 17)):
            self.assertEqual(semana_operacional("08/10/2026")[0], "2026-41")

    def test_compras_atualiza_semana_sem_mudar_quantidade(self):
        original = pd.DataFrame({
            "CÓD": ["00000123"],
            "DATA DA S.C": pd.to_datetime(["2026-10-08"]),
            "QUANTIDADE S.C": [4.0],
        })
        resultados = []
        for dia in (17, 18):
            with patch.object(compras, "hoje_setta", return_value=date(2026, 10, dia)):
                resultado = compras._adicionar_info_semanal(
                    original.copy(), "DATA DA S.C", "QUANTIDADE S.C", "S.C"
                )
            resultados.append(resultado)
        self.assertEqual(resultados[0]["SEMANA DE ATENDIMENTO S.C"].iloc[0], "2026-41")
        self.assertEqual(resultados[1]["SEMANA DE ATENDIMENTO S.C"].iloc[0], "2026-42")
        self.assertEqual(resultados[0]["QUANTIDADE TOTAL DE ATENDIMENTO DA SEMANA S.C"].iloc[0], 4)
        self.assertEqual(resultados[1]["QUANTIDADE TOTAL DE ATENDIMENTO DA SEMANA S.C"].iloc[0], 4)
        self.assertEqual(versao_semana_operacional(date(2026, 10, 18)), 20261018)
