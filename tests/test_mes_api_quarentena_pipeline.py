"""A quarentena MES entra na base derivada sem impedir os materiais válidos."""
import unittest
from unittest.mock import patch

import pandas as pd
import pipeline_sync


CAMPOS = [
    "Linha de origem", "Projeto informado", "Código informado", "Descrição",
    "Qtd. necessária", "Qtd. atendida", "Pendência",
    "Última solicitação", "Motivo", "Status",
    "ORIGEM DO CÓDIGO", "DESCRIÇÃO REFERÊNCIA CADASTROS",
]


class PipelineMESQuarentenaTests(unittest.TestCase):
    def _result(self):
        return {
            "tratado": pd.DataFrame([{"COD_MRP": "23040102007_00000441"}]),
            "inconsistencias": pd.DataFrame(columns=CAMPOS),
            "erros": [],
            "avisos": [],
        }

    def _processar(self, extras):
        files = {key: {"pack": {"sheets": []}} for key in (
            "relatorio_geral", "for001", "for022", "cadastros",
        )}
        with patch.object(pipeline_sync, "_source_frame", return_value=extras), \
             patch.object(pipeline_sync, "_source_sheet_names",
                          return_value=["Geral", "API_INCONSISTENCIAS"]), \
             patch.object(pipeline_sync, "processar_relatorio_geral",
                          return_value=self._result()):
            return pipeline_sync._process("Relatório Geral", files)

    def test_uma_excecao_mes_é_acrescentada_à_quarentena(self):
        row = {
            "Linha de origem": 27322,
            "Projeto informado": "26028901001", "Código informado": "",
            "Descrição": "BASCULANTE", "Qtd. necessária": 1,
            "Qtd. atendida": 0, "Pendência": 1,
            "Última solicitação": "20/10/2026", "Motivo": "Code ausente",
            "Status": "PENDENTE DE REGULARIZAÇÃO",
            "ORIGEM DO CÓDIGO": "MES API",
            "DESCRIÇÃO REFERÊNCIA CADASTROS": "",
        }
        result = self._processar(pd.DataFrame([row], columns=CAMPOS))
        self.assertEqual(len(result["tratado"]), 1)
        self.assertEqual(len(result["inconsistencias"]), 1)
        self.assertEqual(result["inconsistencias"].iloc[0]["Pendência"], 1)
        self.assertEqual(result["inconsistencias"].iloc[0]["Projeto informado"], "26028901001")
        self.assertTrue(any("API MES" in item for item in result["avisos"]))

    def test_quantidade_impossivel_não_se_transforma_em_zero(self):
        data = {x: "" for x in CAMPOS}
        data.update({
            "Linha de origem": 13, "Motivo": "quantidade inválida",
            "Qtd. necessária": "", "Qtd. atendida": 2, "Pendência": "",
        })
        result = self._processar(pd.DataFrame([data]))
        self.assertTrue(pd.isna(result["inconsistencias"].iloc[0]["Pendência"]))

    def test_aba_de_excecoes_com_schema_invalido_bloqueia(self):
        with self.assertRaisesRegex(RuntimeError, "colunas incompatíveis"):
            self._processar(pd.DataFrame([{"Motivo": "sem código"}]))

    def test_planilha_manual_sem_aba_api_continua_compatível(self):
        files = {key: {"pack": {"sheets": []}} for key in (
            "relatorio_geral", "for001", "for022", "cadastros",
        )}
        with patch.object(pipeline_sync, "_source_frame",
                          return_value=pd.DataFrame()), \
             patch.object(pipeline_sync, "_source_sheet_names",
                          return_value=["Geral"]), \
             patch.object(pipeline_sync, "processar_relatorio_geral",
                          return_value=self._result()):
            result = pipeline_sync._process("Relatório Geral", files)
        self.assertEqual(len(result["inconsistencias"]), 0)


if __name__ == "__main__":
    unittest.main()
