"""Compra tratada mantém a identidade de cada S.C. e P.C. por produto."""
import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from conversores.compras import _agrupar_sc, _agrupar_pc, _montar_base_comum


def sc(numero, material="00000395", saldo=1.0, data="06/11/2026"):
    linha = [""] * 14
    linha[0] = numero
    linha[2] = material
    linha[3] = "FIO DE COBRE"
    linha[8] = "600307"
    linha[10] = data
    linha[13] = saldo
    return linha


def pc(numero, material="00000395", quantidade=1.0, entregue=0, data="06/11/2026"):
    linha = [""] * 22
    linha[0] = numero
    linha[7] = material
    linha[9] = "FIO DE COBRE"
    linha[12] = data
    linha[13] = quantidade
    linha[18] = entregue
    linha[21] = "600307"
    return linha


class ComprasPorDocumento(unittest.TestCase):
    def test_sc_mesmo_material_mesma_data_separados(self):
        bruto = pd.DataFrame(
            [sc("034184", saldo=8.13), sc("034196", saldo=10.21)],
            columns=[f"col_{i}" for i in range(14)],
        )
        tratado = _agrupar_sc(bruto)
        self.assertEqual(len(tratado), 2)
        self.assertEqual(tratado["S.C"].tolist(), ["034184", "034196"])
        self.assertEqual(tratado["QUANTIDADE S.C"].tolist(), [8.13, 10.21])

    def test_pc_mesmo_material_mesma_data_separados(self):
        bruto = pd.DataFrame(
            [pc("034139", quantidade=10), pc("034151", quantidade=29, entregue=2)],
            columns=[f"col_{i}" for i in range(22)],
        )
        tratado = _agrupar_pc(bruto)
        self.assertEqual(len(tratado), 2)
        self.assertEqual(tratado["P.C"].tolist(), ["034139", "034151"])
        self.assertEqual(tratado["QUANTIDADE P.C"].tolist(), [10.0, 27.0])

    def test_linhas_repetidas_mesmo_documento_somam_sem_mesclar_documentos(self):
        bruto = pd.DataFrame(
            [sc("034184", saldo=2), sc("034184", saldo=3), sc("034196", saldo=7)],
            columns=[f"col_{i}" for i in range(14)],
        )
        tratado = _agrupar_sc(bruto)
        self.assertEqual(len(tratado), 2)
        mapa = tratado.set_index("S.C")["QUANTIDADE S.C"].to_dict()
        self.assertEqual(mapa, {"034184": 5, "034196": 7})

    def test_base_comum_preserva_documentos_e_totalizadores(self):
        sc_rows = pd.DataFrame(
            [sc("034184", saldo=8), sc("034196", saldo=10)],
            columns=[f"col_{i}" for i in range(14)],
        )
        pc_rows = pd.DataFrame(
            [pc("034139", quantidade=15), pc("034151", quantidade=22)],
            columns=[f"col_{i}" for i in range(22)],
        )
        pre = pd.DataFrame(columns=["CÓD", "PRÉ-NOTA"])
        with patch("conversores.compras.hoje_setta", return_value=date(2026, 11, 6)):
            base = _montar_base_comum(_agrupar_sc(sc_rows), _agrupar_pc(pc_rows), pre)
        self.assertEqual(len(base), 4)
        self.assertEqual(base["QUANTIDADE S.C"].sum(), 18)
        self.assertEqual(base["QUANTIDADE P.C"].sum(), 37)
        self.assertFalse(base["S.C"].astype(str).str.contains(",").any())
        self.assertFalse(base["P.C"].astype(str).str.contains(",").any())


if __name__ == "__main__":
    unittest.main()
