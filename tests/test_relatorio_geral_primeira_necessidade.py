"""Regressões da revisão 6 do Relatório Geral e revisão 3 de endereços."""
import unittest

import pandas as pd

from conversores.relatorio_geral import processar_relatorio_geral
from conversores.estoque import preparar_endereco


class TestNecessidadeNaoDuplicada(unittest.TestCase):
    def setUp(self):
        self.base = {
            "Projeto": "26031401001", "Código": "00060140",
            "Descrição": "TAMPA FINAL",
            "Última solicitação": "13/10/2026",
            "Qtd. necessária": 12, "Qtd. atendida": 4,
            "Resp. separação": "", "Data de separação": "",
            "Resp. conferência": "", "Data de conferência": "",
        }
        self.for001 = pd.DataFrame([[
            "26031401001", *[""] * 11,
            "25/11/2026", "25/11/2026", "NORMAL",
        ]], columns=[f"COL_{i}" for i in range(15)])
        self.for022 = pd.DataFrame([[
            "26031401001", *[""] * 20, "28/11/2026",
        ]], columns=[f"COL_{i}" for i in range(22)])

    def convert(self, linhas):
        return processar_relatorio_geral(
            pd.DataFrame(linhas), self.for001, self.for022
        )

    def test_mesma_op_produto_repetido_por_lote(self):
        primeira = dict(self.base)
        segunda = dict(self.base, **{"Qtd. atendida": 8})
        resultado = self.convert([primeira, segunda])
        self.assertEqual(resultado["erros"], [])
        self.assertEqual(len(resultado["tratado"]), 1)
        row = resultado["tratado"].iloc[0]
        self.assertEqual(row["Qtd. necessária"], 12)
        self.assertEqual(row["Qtd. atendida"], 12)
        self.assertEqual(row["Pendência"], 0)
        self.assertEqual(resultado["metricas"]["op_produto_necessidade_divergente"], 0)

    def test_primeira_linha_rege_mesmo_quando_a_necessidade_varia(self):
        primeira = dict(self.base, **{"Qtd. necessária": 2, "Qtd. atendida": 2})
        segunda = dict(self.base, **{
            "Qtd. necessária": 4, "Qtd. atendida": 4,
            "Última solicitação": "20/10/2026"
        })
        resultado = self.convert([primeira, segunda])
        row = resultado["tratado"].iloc[0]
        self.assertEqual(row["Qtd. necessária"], 2)
        self.assertEqual(row["Qtd. atendida"], 6)
        # Demanda negativa não pode chegar ao MRP por causa de lotes.
        self.assertEqual(row["Pendência"], 0)
        self.assertEqual(resultado["metricas"]["op_produto_necessidade_divergente"], 1)
        self.assertEqual(resultado["metricas"]["op_produto_atendimento_acima_necessidade"], 1)
        self.assertTrue(any("CONFERÊNCIA" in a for a in resultado["avisos"]))

    def test_op_distinta_continua_separada(self):
        primeira = dict(self.base)
        segunda = dict(self.base, Projeto="26031401002")
        resultado = self.convert([primeira, segunda])
        self.assertEqual(len(resultado["tratado"]), 2)
        self.assertEqual(int(resultado["tratado"]["Qtd. necessária"].sum()), 24)


class TestEnderecoSemSaldo(unittest.TestCase):
    def test_exclui_zero_antes_e_depois_de_agrupar(self):
        bruto = pd.DataFrame([
            ["100", "S2", "", "A01", "", "", "", "0"],
            ["100", "S2", "", "A01", "", "", "", "3"],
            ["100", "S2", "", "A02", "", "", "", "2"],
            ["100", "S2", "", "A02", "", "", "", "-2"],
            ["101", "S2", "", "A03", "", "", "", "4"],
        ])
        tratado, erros = preparar_endereco(bruto)
        self.assertEqual(erros, [])
        self.assertEqual(len(tratado), 2)
        self.assertSetEqual(set(tratado["Endereco"]), {"A01", "A03"})
        self.assertEqual(
            float(tratado.loc[tratado["Endereco"] == "A01", "Quantidade"].iloc[0]),
            3.0
        )


if __name__ == "__main__":
    unittest.main()
