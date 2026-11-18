"""PMP 18/11/2026: O (expedição) determina finalização, P reprovação.

Exemplos derivados da estrutura do PMP; não altera arquivos de produção.
"""
import unittest
import pandas as pd

from conversores.tc_tp import (
    _classificar_peca_pmp,
    _preparar_pmp,
    _preparar_h001,
    processar_tc_tp,
)


def pmp(op, status, expedicao=None, finalizacao=None, produto="70150003"):
    return {
        "ORDEM DE PRODUÇÃO": op,
        "CÓDIGO": produto,
        "DESCRIÇÃO": "TC TESTE",
        "DATA ENTREGA CLIENTE": "19/11/2026",
        "DATA DE FINALIZAÇÃO": finalizacao,
        "DATA DE EXPEDIÇÃO": expedicao,
        "STATUS": status,
        "UNIFICADO": produto,
    }


def h001():
    return pd.DataFrame([{
        "PRODUTO": "70150003",
        "MATERIAL": "70020016",
        "DESCRIÇÃO": "COMPONENTE",
        "QTDE_NECESSARIA": 2,
    }])


class ClassificacaoPmpOP(unittest.TestCase):
    def test_com_expedicao_e_finalizada_independente_do_status(self):
        for status in ["EXEC. ADIANTADO", "PROGRAMADO", "REPROVADO"]:
            with self.subTest(status=status):
                self.assertEqual(
                    _classificar_peca_pmp(status, "19/11/2026"),
                    "FINALIZADA_EXPEDIDA",
                )

    def test_sem_expedicao_status_execucao_continua_fabricacao(self):
        for status in [
            "PROGRAMADO", "ATRASADO", "EXEC. ADIANTADO",
            "EXEC. NO PRAZO", "EXEC. ATRASADO", "EM PRODUÇÃO",
        ]:
            with self.subTest(status=status):
                self.assertEqual(
                    _classificar_peca_pmp(status, None), "EM_FABRICACAO"
                )

    def test_sem_expedicao_status_nao_aprovado_nao_e_fabricacao(self):
        for status in [
            "REPROVADA", "REPROVADO", "NÃO APROVADA",
            "REJEITADA", "NOK", "RECUSADO", "SEM APROVAÇÃO",
            "PENDENTE DE APROVAÇÃO", "AGUARDANDO APROVAÇÃO",
            "CANCELADA", "NÃO CONFORME",
        ]:
            with self.subTest(status=status):
                self.assertEqual(
                    _classificar_peca_pmp(status, None), "NAO_APROVADA"
                )

    def test_data_finalizacao_nao_substitui_data_expedicao(self):
        exemplo = pd.DataFrame([pmp(
            "26-1120-01", "EXEC. NO PRAZO",
            expedicao=None, finalizacao="17/11/2026",
        )])
        atual = _preparar_pmp(exemplo, set())
        self.assertEqual(len(atual), 1)
        self.assertEqual(atual.iloc[0]["ORDEM DE PRODUÇÃO"], "26-1120-01")

    def test_explode_h001_so_para_ops_em_fabricacao(self):
        pmp_bruto = pd.DataFrame([
            pmp("26-1120-01", "PROGRAMADO"),
            pmp("26-1120-02", "EXEC. NO PRAZO"),
            pmp("26-1120-03", "EXEC. ADIANTADO", "17/11/2026"),
            pmp("26-1120-04", "REPROVADO"),
        ])
        antes = pmp_bruto.copy(deep=True)
        saida = processar_tc_tp(pmp_bruto, h001())
        self.assertFalse(saida["erros"], saida["erros"])
        self.assertEqual(saida["metricas"]["ofs_em_producao"], 2)
        self.assertEqual(saida["metricas"]["ofs_finalizadas_expedidas"], 1)
        self.assertEqual(saida["metricas"]["ofs_nao_aprovadas"], 1)
        tratado = saida["tratado"]
        self.assertEqual(set(tratado["ORDEM DE PRODUÇÃO"]),
                         {"26-1120-01", "26-1120-02"})
        self.assertEqual(tratado["QUANTIDADE POR OF"].sum(), 4)
        self.assertTrue(
            saida["validacao"]["TIPO"].eq("PEÇA NÃO APROVADA").any()
        )
        self.assertTrue(
            saida["validacao"]["ORDEM DE PRODUÇÃO"].eq("26-1120-04").any()
        )
        pd.testing.assert_frame_equal(pmp_bruto, antes)

    def test_data_expedicao_invalida_bloqueia_fonte(self):
        dados = pd.DataFrame([pmp(
            "26-1120-01", "PROGRAMADO", "NAO_E_UMA_DATA"
        )])
        with self.assertRaisesRegex(ValueError, "DATA DE EXPEDIÇÃO"):
            processar_tc_tp(dados, h001())

    def test_coluna_o_pode_vir_em_diferentes_posicoes_pelo_cabecalho(self):
        dados = pd.DataFrame([
            pmp("26-1120-01", "EXEC. ADIANTADO", None),
            pmp("26-1120-02", "EXEC. ADIANTADO", "17/11/2026"),
        ])
        dados = dados[
            ["STATUS", "DATA DE EXPEDIÇÃO", "CÓDIGO", "ORDEM DE PRODUÇÃO",
             "UNIFICADO", "DATA ENTREGA CLIENTE", "DESCRIÇÃO",
             "DATA DE FINALIZAÇÃO"]
        ]
        result = _preparar_pmp(dados, set())
        self.assertEqual(result["ORDEM DE PRODUÇÃO"].tolist(), ["26-1120-01"])

    def test_sem_bom_mantem_apenas_op_em_fabricacao(self):
        dados = pd.DataFrame([
            pmp("26-1120-01", "EXEC. ATRASADO"),
            pmp("26-1120-02", "REPROVADO"),
            pmp("26-1120-03", "EXEC. ADIANTADO", "16/11/2026"),
        ])
        result = processar_tc_tp(dados, pd.DataFrame(columns=[
            "PRODUTO", "MATERIAL", "DESCRIÇÃO", "QTDE_NECESSARIA"
        ]))
        self.assertEqual(result["tratado"]["ORDEM DE PRODUÇÃO"].tolist(),
                         ["26-1120-01"])
        self.assertEqual(result["tratado"]["MATERIAL"].tolist(), ["00000000"])
        self.assertEqual(result["tratado"]["QUANTIDADE POR OF"].tolist(), [0])


if __name__ == "__main__":
    unittest.main()
