"""Regressões: necessidade por OP/produto/data e saldo de endereços."""
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

    def test_datas_diferentes_sao_solicitacoes_adicionais(self):
        primeira = dict(self.base, **{"Qtd. necessária": 2, "Qtd. atendida": 2})
        segunda = dict(self.base, **{
            "Qtd. necessária": 4, "Qtd. atendida": 4,
            "Última solicitação": "20/10/2026"
        })
        resultado = self.convert([primeira, segunda])
        row = resultado["tratado"].iloc[0]
        self.assertEqual(row["Qtd. necessária"], 6)
        self.assertEqual(row["Qtd. atendida"], 6)
        self.assertEqual(row["Pendência"], 0)
        self.assertEqual(resultado["metricas"]["op_produto_multiplas_solicitacoes"], 1)
        self.assertEqual(resultado["metricas"]["op_produto_necessidade_divergente"], 0)
        self.assertEqual(resultado["metricas"]["op_produto_atendimento_acima_necessidade"], 0)

    def test_lotes_mesma_data_e_nova_solicitacao(self):
        rows = [
            dict(self.base, **{"Qtd. necessária": 3, "Qtd. atendida": 2}),
            dict(self.base, **{"Qtd. necessária": 3, "Qtd. atendida": 1}),
            dict(self.base, **{"Qtd. necessária": 4, "Qtd. atendida": 1,
                                "Última solicitação": "20/10/2026"}),
            dict(self.base, **{"Qtd. necessária": 4, "Qtd. atendida": 3,
                                "Última solicitação": "20/10/2026"}),
        ]
        resultado = self.convert(rows)
        row = resultado["tratado"].iloc[0]
        self.assertEqual(row["Qtd. necessária"], 7)
        self.assertEqual(row["Qtd. atendida"], 7)
        self.assertEqual(row["Pendência"], 0)

    def test_qtd_distinta_na_mesma_data_e_inconsistente(self):
        primeira = dict(self.base, **{"Qtd. necessária": 3, "Qtd. atendida": 1})
        segunda = dict(self.base, **{"Qtd. necessária": 5, "Qtd. atendida": 1})
        resultado = self.convert([primeira, segunda])
        self.assertTrue(resultado["erros"])
        self.assertTrue(resultado["tratado"].empty)
        self.assertTrue(any("mesma OP, produto e data" in msg for msg in resultado["erros"]))

    def test_layout_1311_necessidade_somada_ultima_pendencia(self):
        primeira = dict(self.base, **{
            "Qtd. necessária": 3, "Qtd. atendida": 2,
            "Qtd. pendências": 1, "Lote": "062088",
            "Data de conferência": "23/09/2026",
        })
        segunda = dict(self.base, **{
            "Qtd. necessária": 0, "Qtd. atendida": 1,
            "Qtd. pendências": 0, "Lote": "062136",
            # A ordem de conferência não pode mudar a ultima linha da origem.
            "Data de conferência": "22/09/2026",
        })
        result = self.convert([primeira, segunda])
        self.assertEqual(result["erros"], [])
        linha = result["tratado"].iloc[0]
        self.assertEqual(linha["Qtd. necessária"], 3)
        self.assertEqual(linha["Qtd. atendida"], 3)
        self.assertEqual(linha["Pendência"], 0)
        self.assertEqual(result["metricas"]["op_produto_necessidade_divergente"], 0)

    def test_ultima_pendencia_parcial_e_nao_soma_intermediarias(self):
        linhas = [
            dict(self.base, **{
                "Qtd. necessária": 29, "Qtd. atendida": 3,
                "Qtd. pendências": 26, "Lote": "062088",
            }),
            dict(self.base, **{
                "Qtd. necessária": 0, "Qtd. atendida": 4,
                "Qtd. pendências": 22, "Lote": "062136",
            }),
        ]
        result = self.convert(linhas)
        self.assertEqual(result["erros"], [])
        linha = result["tratado"].iloc[0]
        self.assertEqual(linha["Qtd. necessária"], 29)
        self.assertEqual(linha["Qtd. atendida"], 7)
        self.assertEqual(linha["Pendência"], 22)

    def test_datas_distintas_somam_ultimas_pendencias_individuais(self):
        linhas = [
            dict(self.base, **{
                "Qtd. necessária": 7, "Qtd. atendida": 0,
                "Qtd. pendências": 7,
            }),
            dict(self.base, **{
                "Qtd. necessária": 1, "Qtd. atendida": 0,
                "Qtd. pendências": 1, "Última solicitação": "13/11/2026",
            }),
        ]
        result = self.convert(linhas)
        self.assertEqual(result["erros"], [])
        linha = result["tratado"].iloc[0]
        self.assertEqual(linha["Qtd. necessária"], 8)
        self.assertEqual(linha["Qtd. atendida"], 0)
        self.assertEqual(linha["Pendência"], 8)

    def test_pendencia_fonte_divergente_bloqueia_publicacao(self):
        linhas = [
            dict(self.base, **{
                "Qtd. necessária": 3, "Qtd. atendida": 2,
                "Qtd. pendências": 1,
            }),
            dict(self.base, **{
                "Qtd. necessária": 0, "Qtd. atendida": 1,
                "Qtd. pendências": 1,
            }),
        ]
        result = self.convert(linhas)
        self.assertTrue(result["tratado"].empty)
        self.assertTrue(any("última pendência" in msg for msg in result["erros"]))

    def test_api_sem_k_bloqueia_duas_necessidades_positivas_ambiguas(self):
        linhas = [
            dict(self.base, **{"Qtd. necessária": 3, "Qtd. atendida": 1}),
            dict(self.base, **{"Qtd. necessária": 3, "Qtd. atendida": 1}),
            dict(self.base, **{"Qtd. necessária": 0, "Qtd. atendida": 1}),
        ]
        result = self.convert(linhas)
        self.assertTrue(result["tratado"].empty)
        self.assertTrue(any("sem coluna Qtd. pendências" in msg for msg in result["erros"]))

    def test_api_sem_k_aceita_lotes_adicionais_com_zero(self):
        linhas = [
            dict(self.base, **{"Qtd. necessária": 3, "Qtd. atendida": 2}),
            dict(self.base, **{"Qtd. necessária": 0, "Qtd. atendida": 1}),
        ]
        result = self.convert(linhas)
        self.assertEqual(result["erros"], [])
        linha = result["tratado"].iloc[0]
        self.assertEqual(linha["Qtd. necessária"], 3)
        self.assertEqual(linha["Pendência"], 0)

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
