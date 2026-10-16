"""Testes do disparo semanal do TC/TP, sem acesso à API ou ao Streamlit."""

from datetime import date
import unittest

from conversores.semanas import (
    inicio_semana_operacional,
    semana_operacional,
    versao_semana_operacional,
)


class SemanaOperacionalTests(unittest.TestCase):
    def test_uma_versao_por_semana(self):
        versoes = [
            versao_semana_operacional(date(2026, 10, dia))
            for dia in range(11, 18)
        ]
        self.assertEqual(versoes, [20261011] * 7)

    def test_muda_no_domingo_sem_novo_pmp(self):
        self.assertEqual(versao_semana_operacional(date(2026, 10, 17)), 20261011)
        self.assertEqual(versao_semana_operacional(date(2026, 10, 18)), 20261018)

    def test_fim_do_ano(self):
        self.assertEqual(versao_semana_operacional(date(2027, 1, 1)), 20261227)
        self.assertEqual(versao_semana_operacional(date(2027, 1, 2)), 20261227)
        self.assertEqual(versao_semana_operacional(date(2027, 1, 3)), 20270103)

    def test_domingo_inicial(self):
        self.assertEqual(inicio_semana_operacional(date(2026, 10, 11)), date(2026, 10, 11))
        self.assertEqual(inicio_semana_operacional(date(2026, 10, 17)), date(2026, 10, 11))

    def test_data_vencida_troca_de_semana(self):
        self.assertEqual(
            semana_operacional("08/10/2026", hoje=date(2026, 10, 17))[0],
            "2026-41",
        )
        self.assertEqual(
            semana_operacional("08/10/2026", hoje=date(2026, 10, 18))[0],
            "2026-42",
        )

    def test_mesmas_fontes_nao_reprocessam_ate_domingo(self):
        def desatualizado(anterior, atual):
            return {k: int(v) for k, v in anterior.items()} != {
                k: int(v) for k, v in atual.items()
            }

        anterior = {"pmp": 16, "h001": 6, "semana_operacional_inicio": 20261011}
        mesma_semana = {"pmp": 16, "h001": 6, "semana_operacional_inicio": 20261011}
        novo_domingo = {"pmp": 16, "h001": 6, "semana_operacional_inicio": 20261018}

        self.assertFalse(desatualizado(anterior, mesma_semana))
        self.assertTrue(desatualizado(anterior, novo_domingo))
        self.assertFalse(desatualizado(novo_domingo, novo_domingo))


if __name__ == "__main__":
    unittest.main()
