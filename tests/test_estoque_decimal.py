"""Regressão da leitura decimal do Estoque Tratado (Analítico + Endereço)."""
from __future__ import annotations

import pandas as pd

from conversores.estoque import _numero, processar_estoque
from pipeline_sync import config_for


def raw_row(code: str, label: str, quantity: object) -> list[object]:
    row = [""] * 8
    row[0], row[3], row[7] = code, label, quantity
    return row


def test_separadores() -> None:
    values = pd.Series(
        ["1202.5", "223.5", "1.202,5", "1,202.5", "1.234.567",
         "1,25", "230", 223.5, None, "0", "-2,5"],
        dtype="object",
    )
    expected = [1202.5, 223.5, 1202.5, 1202.5, 1234567.0,
                1.25, 230.0, 223.5, 0.0, 0.0, -2.5]
    parsed = _numero(values).tolist()
    assert parsed == expected, (parsed, expected)


def test_produto_6020072() -> None:
    analitico = pd.DataFrame(
        [raw_row("06020072", "TUBO ESTRUTURAL METALON", "1202.5")]
    )
    endereco = pd.DataFrame([
        raw_row("06020072", "G9-PROD", "223.5"),
        raw_row("06020072", "G9-PROD", "230"),
    ])
    result = processar_estoque(analitico, endereco, ["G9-PROD"])
    assert not result["erros"], result["erros"]
    lines = result["tratado"]
    assert len(lines) == 1
    row = lines.iloc[0]
    assert row["COD_MATERIAL"] == "06020072"
    assert row["SALDO_EM_ESTOQUE"] == 1202.5, row
    assert row["SALDO_NAO_DISPONIVEL"] == 453.5, row
    assert row["SALDO_DISPONIVEL"] == 749, row


def test_revision_forca_recalculo() -> None:
    assert config_for("Saldo em Estoque")["derived_key"] == "estoque_tratado"
    from pathlib import Path
    pipeline = Path("pipeline_sync.py").read_text(encoding="utf-8")
    assert 'versions["revisao_calculo_estoque"] = 2' in pipeline


if __name__ == "__main__":
    test_separadores()
    test_produto_6020072()
    test_revision_forca_recalculo()
    print("ESTOQUE_DECIMAL_6020072_OK")
