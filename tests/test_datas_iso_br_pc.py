"""Regressão crítica de datas do pedido 087058 / material 6050238.

A Central pode normalizar Excel BR para ISO; o conversor nunca deve
reinterpretar 2026-11-02 como 11/02/2026.
"""
import unittest
from datetime import date, datetime

import pandas as pd

from conversores.compras import _data as data_pc, _agrupar_pc, _montar_base_comum
from conversores.semanas import interpretar_data_setta, semana_operacional
from conversores.tc_tp import _data as data_tctp
from conversores.relatorio_geral import _data as data_rg


class DataCompraSeguraTests(unittest.TestCase):
    def test_iso_e_brasileiro_mesmo_dia(self):
        for value in (
            "02/11/2026",
            "2026-11-02",
            "2026-11-02T00:00:00.000",
            "2026-11-02T00:00:00.000Z",
            pd.Timestamp("2026-11-02"),
            datetime(2026,11,2),
            date(2026,11,2),
        ):
            with self.subTest(value=value):
                parsed=interpretar_data_setta(value)
                self.assertEqual(parsed.date(),date(2026,11,2))
                self.assertEqual(data_pc(value).date(),date(2026,11,2))
                self.assertEqual(data_tctp(value).date(),date(2026,11,2))
                self.assertEqual(semana_operacional(value,date(2026,10,23))[0],"2026-44")
                self.assertEqual(semana_operacional(value,date(2026,10,23))[1],"01/11/2026 a 07/11/2026")

    def test_nao_inverte_11_de_fevereiro(self):
        self.assertEqual(interpretar_data_setta("11/02/2026").date(),date(2026,2,11))
        self.assertEqual(interpretar_data_setta("2026-02-11").date(),date(2026,2,11))

    def test_relatorio_geral_misto_iso_br(self):
        vals=data_rg(pd.Series(["2026-11-02","02/11/2026",pd.Timestamp("2026-11-02")]))
        self.assertEqual([x.date() for x in vals], [date(2026,11,2)]*3)

    def test_invalido_nao_inventa_semana(self):
        for value in ("", "31/02/2026", "2026-02-31", "02/11", "NI"):
            self.assertTrue(pd.isna(interpretar_data_setta(value)),value)
            self.assertEqual(semana_operacional(value,date(2026,10,23))[0],"",value)

    def test_pedido_087058_fluxo_integral(self):
        row=[""]*22
        row[0]="087058"             # Nº pedido
        row[7]="6050238"            # H: material
        row[9]="FECHO ESCAMOTEAVEL"  # J: descrição
        row[12]="2026-11-02"        # M: data serializada pela Central
        row[13]=11                   # N: quantidade
        row[18]=0                    # S: entregue
        row[21]="600307"            # V: centro de custo
        bruto=pd.DataFrame([row],columns=[f"Campo_{i}" for i in range(22)])
        pc=_agrupar_pc(bruto)
        self.assertEqual(len(pc),1)
        self.assertEqual(pc.iloc[0]["P.C"],"087058")
        self.assertEqual(pc.iloc[0]["CÓD"],"06050238")
        self.assertEqual(pc.iloc[0]["DATA DA P.C"].date(),date(2026,11,2))
        vazio_sc=pd.DataFrame(columns=["CÓD","DATA DA S.C","DESCRIÇÃO","S.C","QUANTIDADE S.C"])
        vazio_pre=pd.DataFrame(columns=["CÓD","PRÉ-NOTA"])
        # Semana operacional é calculada com data fictícia fixa em teste.
        from unittest.mock import patch
        with patch("conversores.compras.hoje_setta",return_value=date(2026,10,23)):
            tratado=_montar_base_comum(vazio_sc,pc,vazio_pre)
        self.assertEqual(tratado.iloc[0]["DATA DA P.C"],"02/11/2026")
        self.assertEqual(tratado.iloc[0]["SEMANA DE ATENDIMENTO P.C"],"2026-44")
        self.assertEqual(tratado.iloc[0]["QUANTIDADE P.C"],11)
        self.assertEqual(tratado.iloc[0]["QUANTIDADE TOTAL DE ATENDIMENTO DA SEMANA P.C"],11)


if __name__=="__main__":
    unittest.main()
