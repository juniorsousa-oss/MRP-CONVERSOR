"""Cobertura da associação provisória de códigos no CADASTROS."""
import unittest

import pandas as pd

from conversores.cadastro_fallback import recuperar_codigos
from conversores.relatorio_geral import processar_relatorio_geral


class CadastroFallbackTests(unittest.TestCase):
    def setUp(self):
        self.bruto = pd.DataFrame([
            {
                "Projeto": "26028001001",
                "Código": "",
                "Descrição": "BASCULANTE",
                "Última solicitação": "20/10/2026",
                "Qtd. necessária": 11,
                "Qtd. atendida": 0,
                "Resp. separação": "",
                "Data de separação": "",
                "Resp. conferência": "",
                "Data de conferência": "",
            },
            {
                "Projeto": "26028901001",
                "Código": "",
                "Descrição": "BASCULANTE",
                "Última solicitação": "20/10/2026",
                "Qtd. necessária": 1,
                "Qtd. atendida": 0,
                "Resp. separação": "",
                "Data de separação": "",
                "Resp. conferência": "",
                "Data de conferência": "",
            },
        ])

    def cadastro(self, rows):
        return pd.DataFrame(
            [[None, codigo, descricao, tipo] for codigo, descricao, tipo in rows],
            columns=["A", "Código", "Descrição", "Tipo"],
        )

    def test_basculante_unico_recupera_para_os_dois_projetos(self):
        cadastros = self.cadastro([
            ("00543210", "BASCULANTE", "MP"),
            ("00543211", "BUCHA 30MM", "MP"),
        ])
        atualizado, auditoria, candidatos = recuperar_codigos(self.bruto, cadastros)
        self.assertEqual(atualizado["Código"].tolist(), ["00543210", "00543210"])
        self.assertEqual(sum(self.bruto["Qtd. necessária"]), 12)
        self.assertEqual(len(auditoria), 2)
        self.assertEqual(candidatos, [])
        self.assertTrue(
            atualizado["ORIGEM DO CÓDIGO"].eq("CADASTROS - PROVISÓRIO").all()
        )

    def test_duas_opcoes_exatas_impedem_associacao_indiscriminada(self):
        cadastros = self.cadastro([
            ("00543210", "BASCULANTE", "MP"),
            ("00543212", "BASCULANTE", "PI"),
        ])
        atualizado, auditoria, candidatos = recuperar_codigos(self.bruto, cadastros)
        self.assertTrue(atualizado["Código"].eq("").all())
        self.assertEqual(auditoria, [])
        self.assertEqual(len(candidatos), 4)
        self.assertEqual({c["Código candidato"] for c in candidatos}, {"00543210", "00543212"})

    def test_similaridade_curta_so_sugere(self):
        cadastros = self.cadastro([("00543210", "BASCULANTE INDUSTRIAL", "MP")])
        atualizado, auditoria, candidatos = recuperar_codigos(self.bruto, cadastros)
        self.assertTrue(atualizado["Código"].eq("").all())
        self.assertFalse(auditoria)
        self.assertTrue(candidatos)

    def test_termo_generico_em_descricao_extensa_e_sugestao_apenas(self):
        cadastro = self.cadastro([
            ("00543210", "CONJUNTO ESTRUTURAL PARA ACIONAMENTO BASCULANTE SUPERIOR COMPLETO", "MP"),
            ("00543211", "CONECTOR CONTROLE ELETRICO", "MP"),
        ])
        atualizado, auditoria, candidatos = recuperar_codigos(self.bruto, cadastro)
        self.assertEqual(auditoria, [])
        self.assertTrue(atualizado["Código"].eq("").all())
        self.assertEqual({item["Código candidato"] for item in candidatos}, {"00543210"})
        self.assertTrue(all(item["Situação"] == "DESCRICAO_GENERICA_REQUER_CONFERENCIA" for item in candidatos))

    def test_nao_substitui_codigo_fonte(self):
        original = self.bruto.copy()
        original.loc[0, "Código"] = "00000088"
        cadastros = self.cadastro([("00543210", "BASCULANTE", "MP")])
        atualizado, auditoria, _ = recuperar_codigos(original, cadastros)
        self.assertEqual(atualizado.iloc[0]["Código"], "00000088")
        self.assertEqual(atualizado.iloc[0]["ORIGEM DO CÓDIGO"], "RELATÓRIO GERAL")
        self.assertEqual(len(auditoria), 1)

    def test_integracao_agrupamento_preserva_quantidades_e_rastreio(self):
        cadastros = self.cadastro([("00543210", "BASCULANTE", "MP")])
        for001 = pd.DataFrame([
            [projeto, *[""] * 11, "25/11/2026", "25/11/2026", "NORMAL"]
            for projeto in ["26028001001", "26028901001"]
        ], columns=[f"COL_{i}" for i in range(15)])
        for022 = pd.DataFrame([
            [projeto, *[""] * 20, "28/11/2026"]
            for projeto in ["26028001001", "26028901001"]
        ], columns=[f"COL_{i}" for i in range(22)])

        resultado = processar_relatorio_geral(
            self.bruto, for001, for022, cadastros=cadastros
        )
        self.assertEqual(resultado["erros"], [])
        self.assertEqual(len(resultado["tratado"]), 2)
        self.assertEqual(int(resultado["tratado"]["Pendência"].sum()), 12)
        self.assertEqual(resultado["metricas"]["codigos_provisorios"], 2)
        self.assertEqual(resultado["metricas"]["codigos_pendentes"], 0)
        self.assertEqual(
            set(resultado["tratado"]["ORIGEM DO CÓDIGO"]),
            {"CADASTROS - PROVISÓRIO"},
        )


if __name__ == "__main__":
    unittest.main()
