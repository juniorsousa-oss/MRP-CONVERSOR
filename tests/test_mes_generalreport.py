"""Regressão: amostra MES no Teams -> campos e quantitativos do Conversor MRP."""
from __future__ import annotations

from io import BytesIO
import unittest

import pandas as pd

from conversores.mes_generalreport import (
    MES_TO_GERAL, adaptar_json_mes, adaptar_json_mes_com_quarentena,
    exportar_geral_excel, diagnostico_mes,
)
from conversores.relatorio_geral import processar_relatorio_geral


def registro(**updates):
    row = {
        "OP": "23040102007",
        "PA": "52700375",
        "DescriptionPA": "POWER-BALT SETTA",
        "Code": "00000441",
        "Batch": "061638",
        "Description": "CABO DE COMUNICACAO",
        "LastRequest": "2026-08-11T15:46:19.714Z",
        "NecessaryQuantity": 1,
        "AttendedQuantity": 1,
        "SeparationUser": "USUARIO TESTE",
        "SeparationDate": "2026-09-18T13:39:23.611Z",
        "ConferenceResponse": "CONFERENTE TESTE",
        "ConferenceDate": "2026-09-23T11:31:02.981Z",
        "Progress": "93,75%",
        "Reported": False,
        "Reference": "",
        "Supplier": "FORNECEDOR TESTE",
        "UserUpdateSA": "USUARIO TESTE",
        "Minimum_Value_Found": 0,
        "Lead_Time_Minimum_Price": 0,
    }
    row.update(updates)
    return row


class AdaptadorGeneralReportTests(unittest.TestCase):
    def test_um_sem_codigo_em_201_nao_bloqueia_base_valida(self):
        rows = [
            registro(Code="00000441", NecessaryQuantity=1, AttendedQuantity=0)
            for _ in range(200)
        ]
        rows.append(registro(Code=None, Description="BASCULANTE",
                             NecessaryQuantity=1, AttendedQuantity=0))
        result = adaptar_json_mes_com_quarentena(rows, linhas_referencia=201)
        self.assertTrue(result["pode_processar"])
        self.assertEqual(result["status"], "PROCESSAR_COM_RESSALVAS")
        self.assertEqual(len(result["tratado"]), 200)
        self.assertEqual(len(result["inconsistencias"]), 1)
        self.assertEqual(result["metricas"]["linhas_recebidas"], 201)
        self.assertEqual(result["inconsistencias"].iloc[0]["Linha JSON"], 201)
        self.assertEqual(result["inconsistencias"].iloc[0]["Qtd. necessária informada"], 1)
        self.assertEqual(result["inconsistencias"].iloc[0]["Status"], "PENDENTE DE REGULARIZAÇÃO")

    def test_outro_erro_isolado_e_informado_sem_contaminar_demanda(self):
        rows = [registro() for _ in range(200)]
        rows.append(registro(AttendedQuantity="N/A"))
        result = adaptar_json_mes_com_quarentena(rows)
        self.assertTrue(result["pode_processar"])
        self.assertEqual(result["status"], "PROCESSAR_COM_RESSALVAS")
        self.assertEqual(len(result["tratado"]), 200)
        self.assertIn("não é numérico", result["inconsistencias"].iloc[0]["Motivo"])

    def test_muitos_erros_protegem_ultima_fonte(self):
        rows = [registro() for _ in range(10)]
        rows.extend(registro(Code=None) for _ in range(10))
        result = adaptar_json_mes_com_quarentena(rows)
        self.assertFalse(result["pode_processar"])
        self.assertEqual(result["status"], "PROTEGER_BASE")
        self.assertEqual(len(result["tratado"]), 10)
        self.assertEqual(len(result["inconsistencias"]), 10)

    def test_resposta_muito_menor_que_referencia_nao_pode_publicar(self):
        result = adaptar_json_mes_com_quarentena([registro()], linhas_referencia=100)
        self.assertFalse(result["pode_processar"])
        self.assertEqual(result["status"], "PROTEGER_BASE")

    def test_adaptador_estrito_antigo_permanece_compativel(self):
        with self.assertRaisesRegex(ValueError, "Code"):
            adaptar_json_mes([registro(Code=None)])

    def test_campos_mes_para_geral_preservam_op_codigo_e_qtd(self):
        df = adaptar_json_mes([registro()])
        self.assertEqual(list(df.columns), list(MES_TO_GERAL.values()))
        linha = df.iloc[0]
        self.assertEqual(linha["Projeto"], "23040102007")
        self.assertEqual(linha["Código"], "00000441")
        self.assertEqual(linha["Descrição"], "CABO DE COMUNICACAO")
        self.assertEqual(linha["Última solicitação"], "11/08/2026")
        self.assertEqual(linha["Qtd. necessária"], 1)
        self.assertEqual(linha["Qtd. atendida"], 1)

    def test_lotes_e_codigos_nao_sao_agrupados_no_adaptador(self):
        df = adaptar_json_mes([
            registro(Batch="061638", AttendedQuantity=0.4),
            registro(Batch="061639", AttendedQuantity=0.6),
            registro(Code="00000444", Description="CABO EXTENSOR"),
        ])
        self.assertEqual(len(df), 3)
        self.assertEqual(df["Qtd. necessária"].tolist(), [1.0, 1.0, 1.0])
        self.assertAlmostEqual(df["Qtd. atendida"].sum(), 2.0)
        self.assertEqual(df["Código"].tolist(), ["00000441", "00000441", "00000444"])

    def test_quantidades_invalidas_nao_geram_demanda_ficticia(self):
        for valor in [None, "N/A", -1, True, "NaN"]:
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    adaptar_json_mes([registro(NecessaryQuantity=valor)])

    def test_campos_criticos_ausentes_bloqueiam(self):
        dados = registro()
        del dados["AttendedQuantity"]
        with self.assertRaisesRegex(ValueError, "AttendedQuantity"):
            adaptar_json_mes([dados])

    def test_json_vazio_e_objeto_incorreto_bloqueiam(self):
        for payload in ([], {}, {"data": {}}, {"data": []}, "texto"):
            with self.subTest(payload=str(payload)):
                with self.assertRaises(ValueError):
                    adaptar_json_mes(payload)

    def test_wrapper_data_pode_ser_lido(self):
        df = adaptar_json_mes({"data": [registro()]})
        self.assertEqual(len(df), 1)

    def test_iso_utc_em_horario_de_madrugada_usa_data_brasil(self):
        df = adaptar_json_mes([registro(LastRequest="2026-09-18T01:30:00Z")])
        self.assertEqual(df.iloc[0]["Última solicitação"], "17/09/2026")

    def test_codigo_numerico_recebe_zero_a_esquerda(self):
        df = adaptar_json_mes([registro(Code=441)])
        self.assertEqual(df.iloc[0]["Código"], "00000441")

    def test_excel_exportado_mantem_aba_geral_e_codigos_texto(self):
        raw = exportar_geral_excel(adaptar_json_mes([registro()]))
        restored = pd.read_excel(BytesIO(raw), sheet_name="Geral", dtype={"Código": str, "Projeto": str})
        self.assertEqual(restored.iloc[0]["Código"], "00000441")
        self.assertEqual(restored.iloc[0]["Projeto"], "23040102007")
        self.assertEqual(restored.iloc[0]["Qtd. necessária"], 1)

    def test_lotes_nao_duplicam_necessidade_ao_entrar_no_conversor(self):
        bruto = adaptar_json_mes([
            registro(Code="00000441", Batch="061638", NecessaryQuantity=2, AttendedQuantity=1),
            registro(Code="00000441", Batch="061639", NecessaryQuantity=2, AttendedQuantity=1),
        ])
        for001 = pd.DataFrame([["23040102007", *[""] * 11, "25/11/2026", "25/11/2026", "NORMAL"]],
                              columns=[f"COL_{i}" for i in range(15)])
        for022 = pd.DataFrame([["23040102007", *[""] * 20, "28/11/2026"]],
                              columns=[f"COL_{i}" for i in range(22)])
        result = processar_relatorio_geral(bruto, for001, for022)
        self.assertEqual(result["erros"], [])
        item = result["tratado"].iloc[0]
        self.assertEqual(item["Qtd. necessária"], 2)
        self.assertEqual(item["Qtd. atendida"], 2)
        self.assertEqual(item["Pendência"], 0)

    def test_diagnostico_sem_dados_pessoais(self):
        stats = diagnostico_mes(adaptar_json_mes([registro()]))
        self.assertEqual(stats["linhas"], 1)
        self.assertEqual(stats["materiais"], 1)
        self.assertNotIn("USUARIO TESTE", str(stats))
        self.assertNotIn("FORNECEDOR TESTE", str(stats))


if __name__ == "__main__":
    unittest.main()
