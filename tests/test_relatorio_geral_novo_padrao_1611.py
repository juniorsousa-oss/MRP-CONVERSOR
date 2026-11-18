"""Regressao da consolidação por lote no Relatorio Geral MES de 16/11."""
import unittest
import pandas as pd

from conversores.relatorio_geral import processar_relatorio_geral


OP = "23040102007"
CODE = "00060140"


def dados(**overrides):
    linha = {
        "Projeto": OP, "Código": CODE, "Descrição": "CABO",
        "Última solicitação": "13/11/2026",
        "Qtd. necessária": 2, "Qtd. atendida": 2,
        "Qtd. pendências": 0,
        "Resp. separação": "", "Data de separação": "",
        "Resp. conferência": "", "Data de conferência": "",
        "Lote": "062088",
    }
    linha.update(overrides)
    return linha


class ContratoMESNovo(unittest.TestCase):
    def setUp(self):
        self.for001 = pd.DataFrame([[
            OP, *[""] * 11, "25/11/2026", "25/11/2026", "NORMAL"
        ]], columns=[f"COL_{i}" for i in range(15)])
        self.for022 = pd.DataFrame([[
            OP, *[""] * 20, "28/11/2026"
        ]], columns=[f"COL_{i}" for i in range(22)])

    def processar(self, rows):
        return processar_relatorio_geral(
            pd.DataFrame(rows), self.for001, self.for022
        )

    def test_lotes_com_necessidade_positiva_igual_somam_ambos(self):
        resultado = self.processar([
            dados(Lote="062088"),
            dados(Lote="062136"),
        ])
        self.assertEqual(resultado["erros"], [])
        linha = resultado["tratado"].iloc[0]
        self.assertEqual(linha["Qtd. necessária"], 4)
        self.assertEqual(linha["Qtd. atendida"], 4)
        self.assertEqual(linha["Pendência"], 0)
        self.assertEqual(
            resultado["metricas"]["modo_consolidacao_pendencia"],
            "NOVO_16_11_POR_LINHA",
        )

    def test_necessidades_parciais_somam_e_pendencia_soma(self):
        resultado = self.processar([
            dados(Lote="062088", **{"Qtd. necessária": 5,
                                   "Qtd. atendida": 2,
                                   "Qtd. pendências": 3}),
            dados(Lote="062136", **{"Qtd. necessária": 3,
                                   "Qtd. atendida": 0,
                                   "Qtd. pendências": 3}),
        ])
        self.assertEqual(resultado["erros"], [])
        linha = resultado["tratado"].iloc[0]
        self.assertEqual(linha["Qtd. necessária"], 8)
        self.assertEqual(linha["Qtd. atendida"], 2)
        self.assertEqual(linha["Pendência"], 6)

    def test_solicitacoes_diferentes_mantem_pendencias_separadas(self):
        resultado = self.processar([
            dados(**{"Qtd. necessária": 5, "Qtd. atendida": 2,
                     "Qtd. pendências": 3}),
            dados(**{"Última solicitação": "16/11/2026",
                     "Qtd. necessária": 2, "Qtd. atendida": 2,
                     "Qtd. pendências": 0}),
        ])
        self.assertEqual(resultado["erros"], [])
        linha = resultado["tratado"].iloc[0]
        self.assertEqual(linha["Qtd. necessária"], 7)
        self.assertEqual(linha["Qtd. atendida"], 4)
        self.assertEqual(linha["Pendência"], 3)

    def test_valor_minimo_positivo_preservado_sem_somar_lotes(self):
        resultado = self.processar([
            dados(Lote="062088", **{"Qtd. necessária": 4,
                                   "Qtd. atendida": 0,
                                   "Qtd. pendências": 4,
                                   "Valor mínimo encontrado": "12,50"}),
            dados(Lote="062136", **{"Qtd. necessária": 2,
                                   "Qtd. atendida": 0,
                                   "Qtd. pendências": 2,
                                   "Valor mínimo encontrado": 11.25}),
            dados(Lote="062137", **{"Qtd. necessária": 1,
                                   "Qtd. atendida": 0,
                                   "Qtd. pendências": 1,
                                   "Valor mínimo encontrado": 0}),
        ])
        self.assertEqual(resultado["erros"], [])
        linha = resultado["tratado"].iloc[0]
        self.assertEqual(linha["Qtd. necessária"], 7)
        self.assertEqual(linha["Pendência"], 7)
        self.assertEqual(linha["Valor mínimo encontrado"], 11.25)

    def test_layout_mais_antigo_sem_preco_continua_compativel(self):
        resultado = self.processar([
            dados(**{"Qtd. necessária": 3, "Qtd. atendida": 1,
                     "Qtd. pendências": 2}),
        ])
        self.assertEqual(resultado["erros"], [])
        self.assertEqual(resultado["tratado"].iloc[0]["Valor mínimo encontrado"], 0)

    def test_arquivo_antigo_ainda_utiliza_ultima_pendencia(self):
        resultado = self.processar([
            dados(**{"Qtd. necessária": 3, "Qtd. atendida": 2,
                     "Qtd. pendências": 1}),
            dados(Lote="062136", **{"Qtd. necessária": 0,
                                    "Qtd. atendida": 1,
                                    "Qtd. pendências": 0}),
        ])
        self.assertEqual(resultado["erros"], [])
        linha = resultado["tratado"].iloc[0]
        self.assertEqual(linha["Qtd. necessária"], 3)
        self.assertEqual(linha["Pendência"], 0)
        self.assertEqual(
            resultado["metricas"]["modo_consolidacao_pendencia"],
            "LEGADO_13_11_SALDO_FINAL",
        )

    def test_fonte_com_pendencia_sem_conciliacao_nao_publica(self):
        resultado = self.processar([
            dados(**{"Qtd. necessária": 3, "Qtd. atendida": 2,
                     "Qtd. pendências": 2}),
        ])
        self.assertTrue(resultado["erros"])
        self.assertTrue(resultado["tratado"].empty)
        self.assertIn("última pendência", " ".join(resultado["erros"]))


if __name__ == "__main__":
    unittest.main()
