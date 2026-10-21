"""Protege o MRP de rodapés vazios sem descartar demanda sem código."""
import unittest

import pandas as pd

from conversores.relatorio_geral import processar_relatorio_geral


class TestRelatorioGeralSemCodigo(unittest.TestCase):
    def setUp(self):
        self.linha = {
            "Projeto": "26031401001",
            "Código": "06020072",
            "Descrição": "MATERIAL DE TESTE",
            "Última solicitação": "13/10/2026",
            "Qtd. necessária": 10,
            "Qtd. atendida": 2,
            "Resp. separação": "",
            "Data de separação": "",
            "Resp. conferência": "",
            "Data de conferência": "",
        }
        self.for001 = pd.DataFrame([[
            "26031401001", *[""] * 11, "25/11/2026",
            "25/11/2026", "NORMAL",
        ]], columns=[f"COL_{i}" for i in range(15)])
        self.for022 = pd.DataFrame([[
            "26031401001", *[""] * 20, "28/11/2026",
        ]], columns=[f"COL_{i}" for i in range(22)])

    def _run(self, rows):
        return processar_relatorio_geral(pd.DataFrame(rows), self.for001, self.for022)

    def test_linha_estrutural_totalmente_vazia_nao_bloqueia_processamento(self):
        rodape = {key: "" for key in self.linha}
        rodape["Projeto"] = "26031401001"
        rodape["Qtd. necessária"] = 0
        rodape["Qtd. atendida"] = 0
        result = self._run([self.linha, rodape])
        self.assertEqual(result["erros"], [])
        self.assertEqual(len(result["tratado"]), 1)
        self.assertEqual(result["tratado"].iloc[0]["Pendência"], 8)
        self.assertTrue(any("linha(s) sem código" in msg for msg in result["avisos"]))

    def test_linha_sem_codigo_com_demanda_bloqueia_publicacao(self):
        invalida = dict(self.linha)
        invalida["Código"] = ""
        invalida["Qtd. necessária"] = 8
        result = self._run([self.linha, invalida])
        self.assertTrue(any("Código vazio" in msg for msg in result["erros"]))
        self.assertTrue(any("validação(ões) de código falharam" in msg for msg in result["erros"]))

    def test_linha_sem_codigo_com_descricao_nao_e_descartada(self):
        invalida = dict(self.linha)
        invalida["Código"] = ""
        invalida["Qtd. necessária"] = 0
        invalida["Qtd. atendida"] = 0
        result = self._run([self.linha, invalida])
        self.assertTrue(any("Código vazio" in msg for msg in result["erros"]))


if __name__ == "__main__":
    unittest.main()
