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

    def test_linha_sem_codigo_com_demanda_vai_para_quarentena(self):
        invalida = dict(self.linha)
        invalida["Código"] = ""
        invalida["Qtd. necessária"] = 8
        result = self._run([self.linha, invalida])
        self.assertEqual(result["erros"], [])
        self.assertEqual(len(result["tratado"]), 1)
        self.assertEqual(int(result["tratado"]["Pendência"].sum()), 8)
        self.assertEqual(len(result["inconsistencias"]), 1)
        self.assertEqual(int(result["inconsistencias"]["Pendência"].sum()), 8)
        self.assertIn("Código vazio", result["inconsistencias"].iloc[0]["Motivo"])
        self.assertTrue(any("fora do MRP" in msg for msg in result["avisos"]))

    def test_linha_sem_codigo_com_descricao_nao_e_descartada(self):
        invalida = dict(self.linha)
        invalida["Código"] = ""
        invalida["Qtd. necessária"] = 0
        invalida["Qtd. atendida"] = 0
        result = self._run([self.linha, invalida])
        self.assertEqual(result["erros"], [])
        self.assertEqual(len(result["inconsistencias"]), 1)
        self.assertEqual(result["inconsistencias"].iloc[0]["Descrição"], "MATERIAL DE TESTE")

    def test_quatro_linhas_basculante_preservam_projetos_e_total(self):
        base = dict(self.linha)
        linhas = [base]
        for projeto, quantidade in [
            ("26028001001", 5),
            ("26028001001", 6),
            ("26028901001", 1),
            ("26028901001", 0),
        ]:
            invalida = dict(base)
            invalida.update({
                "Projeto": projeto,
                "Código": "",
                "Descrição": "BASCULANTE",
                "Qtd. necessária": quantidade,
                "Qtd. atendida": 0,
            })
            linhas.append(invalida)
        result = self._run(linhas)
        self.assertEqual(result["erros"], [])
        self.assertEqual(len(result["inconsistencias"]), 4)
        self.assertEqual(int(result["inconsistencias"]["Pendência"].sum()), 12)
        self.assertEqual(set(result["inconsistencias"]["Projeto informado"]), {
            "26028001001", "26028901001",
        })
        self.assertEqual(int(result["tratado"]["Pendência"].sum()), 8)
        self.assertTrue(result["tratado"]["Código"].str.fullmatch(r"\\d{8}").all())

    def test_100_por_cento_invalido_nao_sobrescreve_base_existente(self):
        invalida = dict(self.linha)
        invalida.update({"Código": "", "Qtd. necessária": 11})
        result = self._run([invalida])
        self.assertTrue(result["erros"])
        self.assertTrue(result["tratado"].empty)
        self.assertEqual(len(result["inconsistencias"]), 1)


if __name__ == "__main__":
    unittest.main()
