"""Teste da quarentena MES na base derivada do Conversor MRP."""
import unittest
from unittest.mock import patch

import pandas as pd

import pipeline_sync as p


class QuarentenaMesPipelineTests(unittest.TestCase):
    @staticmethod
    def exemplo_resultado():
        base = pd.DataFrame([{
            "Código": "00000441", "Projeto": "26028901001",
            "Pendência": 2,
        }])
        vazio = pd.DataFrame(columns=[
            "Linha de origem", "Projeto informado", "Código informado",
            "Descrição", "Qtd. necessária", "Qtd. atendida", "Pendência",
            "Última solicitação", "Motivo", "Status", "ORIGEM DO CÓDIGO",
            "DESCRIÇÃO REFERÊNCIA CADASTROS",
        ])
        return {"tratado": base, "inconsistencias": vazio, "erros": [], "avisos": []}

    @staticmethod
    def mes_sidecar():
        return pd.DataFrame([{
            "Linha JSON": 27322,
            "Projeto informado": "26028901001",
            "Código informado": None,
            "Descrição": "BASCULANTE",
            "Qtd. necessária informada": 1,
            "Qtd. atendida informada": 0,
            "Motivo": "REGISTRO INCONSISTENTE NA ORIGEM MES",
            "Status": "PENDENTE DE REGULARIZAÇÃO",
        }])

    def test_material_sem_codigo_so_na_quarentena(self):
        result = self.exemplo_resultado()
        with patch.object(p, "_source_sheet_names",
                          return_value=["Geral", "Inconsistencias MES"]), \
             patch.object(p, "_source_frame", return_value=self.mes_sidecar()):
            novo = p._incorporar_quarentena_mes(result, {"pack": {}})
        self.assertEqual(len(novo["tratado"]), 1)
        self.assertEqual(len(novo["inconsistencias"]), 1)
        row = novo["inconsistencias"].iloc[0]
        self.assertEqual(row["Pendência"], 1)
        self.assertEqual(row["Descrição"], "BASCULANTE")
        self.assertEqual(row["Projeto informado"], "26028901001")
        self.assertEqual(row["Status"], "PENDENTE DE REGULARIZAÇÃO")
        self.assertIn("MES", row["ORIGEM DO CÓDIGO"])

    def test_excel_legado_sem_sidecar_nao_muda(self):
        result = self.exemplo_resultado()
        with patch.object(p, "_source_sheet_names", return_value=["Geral"]):
            novo = p._incorporar_quarentena_mes(result, {"pack": {}})
        self.assertIs(novo, result)

    def test_quarentena_invalidas_nao_pode_sumir_silenciosamente(self):
        sidecar = self.mes_sidecar().drop(columns=["Motivo"])
        with patch.object(p, "_source_sheet_names",
                          return_value=["Geral", "Inconsistencias MES"]), \
             patch.object(p, "_source_frame", return_value=sidecar):
            with self.assertRaisesRegex(ValueError, "incompleta"):
                p._incorporar_quarentena_mes(self.exemplo_resultado(), {"pack": {}})

    def test_quantidade_irregular_conserva_texto_sem_gerar_valor_falso(self):
        sidecar = self.mes_sidecar()
        sidecar.loc[0, "Qtd. necessária informada"] = "invalida"
        with patch.object(p, "_source_sheet_names",
                          return_value=["Geral", "Inconsistencias MES"]), \
             patch.object(p, "_source_frame", return_value=sidecar):
            result = p._incorporar_quarentena_mes(self.exemplo_resultado(), {"pack": {}})
        row = result["inconsistencias"].iloc[0]
        self.assertEqual(row["Qtd. necessária"], "invalida")
        self.assertTrue(pd.isna(row["Pendência"]))


if __name__ == "__main__":
    unittest.main()
