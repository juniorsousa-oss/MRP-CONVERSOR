"""Protege a seleção segura da aba de Pedido de Compras autorizado."""
import unittest
from unittest.mock import patch
import pandas as pd
import pipeline_sync


def pc_frame(cost_center="600307", width=22):
    row = [""] * width
    if width >= 22:
        row[21] = cost_center
    return pd.DataFrame([row], columns=[f"col_{i}" for i in range(width)])


class PedidoComprasSheetTests(unittest.TestCase):
    def verify(self, names, frames, expected):
        with patch.object(pipeline_sync, "_source_sheet_names", return_value=names):
            with patch.object(
                pipeline_sync, "_source_frame",
                side_effect=lambda source, sheet_name, header: frames[sheet_name],
            ):
                self.assertEqual(pipeline_sync._select_pc_sheet({}), expected)

    def test_original_name(self):
        name = "2-Pedido de Compras   Autoriz"
        self.verify([name], {name: pc_frame()}, name)

    def test_changed_spacing_and_accent(self):
        name = "2 - Pedido de Compras Autoriz."
        self.verify([name], {name: pc_frame()}, name)

    def test_renamed_authorized_sheet_not_first(self):
        name = "2 - Pedido de Compras Autorizados"
        self.verify(["Resumo", name], {"Resumo": pc_frame(width=8), name: pc_frame()}, name)

    def test_structural_fallback_uses_cost_center_and_width(self):
        name = "Relatorio 2"
        self.verify(
            ["Resumo", name],
            {"Resumo": pc_frame(width=8), name: pc_frame("600307.0")},
            name,
        )

    def test_rejects_sheet_missing_required_columns(self):
        name = "2-Pedido de Compras Autoriz"
        with patch.object(pipeline_sync, "_source_sheet_names", return_value=[name]):
            with patch.object(pipeline_sync, "_source_frame", return_value=pc_frame(width=21)):
                with self.assertRaisesRegex(ValueError, "pelo menos 22"):
                    pipeline_sync._select_pc_sheet({})

    def test_ambiguous_fallback_must_not_pick_arbitrarily(self):
        with patch.object(pipeline_sync, "_source_sheet_names", return_value=["Plan1", "Plan2"]):
            with patch.object(pipeline_sync, "_source_frame", return_value=pc_frame()):
                with self.assertRaisesRegex(ValueError, "Abas disponíveis"):
                    pipeline_sync._select_pc_sheet({})


if __name__ == "__main__":
    unittest.main()
