"""Testes offline do executor que não exigem a API nem Streamlit aberto."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sync_all_headless", ROOT / "scripts" / "sync_all_headless.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PipelineFalso:
    PIPELINES = {"Relatório Geral": {}, "MRP — TC/TP": {}}
    def __init__(self, stale: bool = False, status: str = "ATUALIZADO"):
        self.chamados = []
        self.stale = stale
        self.status = status
    def get_state(self, name):
        self.chamados.append(("check", name))
        return {"stale": self.stale, "ready": True, "versions": {"pmp": 22}}
    def sync_pipeline(self, name, force=False):
        self.chamados.append(("sync", name, force))
        return {"sync_status": self.status, "versions": {"pmp": 22}}


class HeadlessTests(unittest.TestCase):
    def test_verificar_nao_publica(self):
        pipe = PipelineFalso(stale=True)
        self.assertEqual(module.execute(pipe, check=True), 0)
        self.assertEqual(len(pipe.chamados), 2)
        self.assertTrue(all(item[0] == "check" for item in pipe.chamados))
    def test_roda_todos_sem_forcar(self):
        pipe = PipelineFalso()
        self.assertEqual(module.execute(pipe), 0)
        self.assertEqual(pipe.chamados, [
            ("sync", "Relatório Geral", False),
            ("sync", "MRP — TC/TP", False),
        ])
    def test_limita_a_um_relatorio(self):
        pipe = PipelineFalso()
        self.assertEqual(module.execute(pipe, only="MRP — TC/TP"), 0)
        self.assertEqual(pipe.chamados, [("sync", "MRP — TC/TP", False)])
    def test_falha_do_pipeline_falha_job(self):
        pipe = PipelineFalso(status="ERRO")
        self.assertEqual(module.execute(pipe), 1)
    def test_espera_por_fontes_nao_passar_despercebido(self):
        pipe = PipelineFalso(status="AGUARDANDO")
        self.assertEqual(module.execute(pipe), 1)


if __name__ == "__main__":
    unittest.main()
