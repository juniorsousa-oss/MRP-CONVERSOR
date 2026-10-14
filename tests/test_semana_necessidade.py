"""Regressão: semana de necessidade deve considerar Data MRP - 30 dias."""
import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from conversores.relatorio_geral import processar_relatorio_geral


class TestSemanaDeNecessidade(unittest.TestCase):
    def _executar(self, data_mrp, data_cliente="25/11/2026"):
        bruto = pd.DataFrame([{
            "Projeto": "26031401001",
            "Código": "06020072",
            "Descrição": "TUBO ESTRUTURAL METALON",
            "Última solicitação": "13/10/2026",
            "Qtd. necessária": 420,
            "Qtd. atendida": 0,
            "Resp. separação": "",
            "Data de separação": "",
            "Resp. conferência": "",
            "Data de conferência": "",
        }])
        # FOR-001: A=OP, M=Data Cliente, N=Data MRP, O=Condição.
        for001_cols = [f"COL_{i}" for i in range(15)]
        for001 = pd.DataFrame([[
            "26031401001", *[""] * 11,
            data_cliente, data_mrp, "NORMAL",
        ]], columns=for001_cols)
        # FOR-022: A=OP, V=Data de Separação.
        for022 = pd.DataFrame([[
            "26031401001", *[""] * 20, "28/11/2026",
        ]], columns=[f"COL_{i}" for i in range(22)])
        with patch("conversores.relatorio_geral.date") as data_mock:
            data_mock.today.return_value = date(2026, 10, 14)
            return processar_relatorio_geral(bruto, for001, for022)

    def test_op_26031401001_antecipa_30_dias(self):
        resultado = self._executar("25/11/2026")
        self.assertEqual(resultado["erros"], [])
        item = resultado["tratado"].iloc[0]
        self.assertEqual(item["DATA MRP"], "25/11/2026")
        self.assertEqual(item["SEMANA DE NECESSIDADE"], "2026-43")
        self.assertEqual(item["PERIODO DA SEMANA"], "25/10/2026 a 31/10/2026")
        self.assertEqual(item["VINCULAÇÃO DA DATA"], "DATA MRP")
        self.assertEqual(item["NECESSIDADE DA SEMANA"], 420)

    def test_sem_data_mrp_preserva_fallback_cliente(self):
        resultado = self._executar("", "25/11/2026")
        self.assertEqual(resultado["erros"], [])
        item = resultado["tratado"].iloc[0]
        self.assertEqual(item["DATA MRP"], "25/11/2026")
        self.assertEqual(item["SEMANA DE NECESSIDADE"], "2026-43")
        self.assertEqual(item["VINCULAÇÃO DA DATA"], "DATA CLIENTE")

    def test_data_vencida_fica_na_semana_atual(self):
        resultado = self._executar("12/10/2026")
        self.assertEqual(resultado["erros"], [])
        item = resultado["tratado"].iloc[0]
        self.assertEqual(item["DATA MRP"], "12/10/2026")
        self.assertEqual(item["SEMANA DE NECESSIDADE"], "2026-41")


if __name__ == "__main__":
    unittest.main()
