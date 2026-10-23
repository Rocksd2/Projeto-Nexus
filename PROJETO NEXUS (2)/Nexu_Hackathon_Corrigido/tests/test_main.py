"""Testes de regressão para as regras críticas do Nexu."""
import os
import tempfile
import unittest
from pathlib import Path

# Evita que a importação do servidor inicialize/modifique o banco de demonstração.
_TEST_IMPORT_DIR = tempfile.TemporaryDirectory()
os.environ["NEXU_DB_PATH"] = str(Path(_TEST_IMPORT_DIR.name) / "import.db")
import main


class NexuAPITests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = main.DB_PATH
        main.DB_PATH = Path(self.tempdir.name) / "test.db"
        main.inicializar_banco()
        self.client = main.app.test_client()

    def tearDown(self):
        main.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def criar_produto(self, estoque=5):
        response = self.client.post("/api/produtos", json={
            "produto": "Arroz", "categoria": "Mercearia",
            "preco_compra": 5.00, "preco_venda": 8.00, "estoque": estoque,
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["id"]

    def obter_produto(self, produto_id):
        return next(p for p in self.client.get("/api/produtos").get_json()
                    if p["id"] == produto_id)

    def test_venda_valida_baixa_estoque_e_registra_historico(self):
        produto_id = self.criar_produto(5)
        response = self.client.post("/api/vendas/lote", json={
            "itens": [{"id": produto_id, "qtd": 2}]
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(self.obter_produto(produto_id)["estoque"], 3)
        historico = self.client.get("/api/vendas").get_json()
        self.assertEqual(len(historico), 1)
        self.assertEqual(historico[0]["quantidade"], 2)
        self.assertAlmostEqual(historico[0]["total"], 16.00)

    def test_rejeita_quantidade_negativa_zero_e_fracionaria(self):
        produto_id = self.criar_produto(5)
        for qtd in (-1, 0, 1.5, True, "1.5"):
            with self.subTest(qtd=qtd):
                response = self.client.post("/api/vendas/lote", json={
                    "itens": [{"id": produto_id, "qtd": qtd}]
                })
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.obter_produto(produto_id)["estoque"], 5)
        self.assertEqual(self.client.get("/api/vendas").get_json(), [])

    def test_rejeita_estoque_excedido_com_produto_repetido_no_carrinho(self):
        produto_id = self.criar_produto(5)
        response = self.client.post("/api/vendas/lote", json={
            "itens": [{"id": produto_id, "qtd": 4}, {"id": produto_id, "qtd": 4}]
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.obter_produto(produto_id)["estoque"], 5)
        self.assertEqual(self.client.get("/api/vendas").get_json(), [])

    def test_venda_lote_invalida_nao_processa_parcialmente(self):
        p1 = self.criar_produto(5)
        p2 = self.client.post("/api/produtos", json={
            "produto": "Feijão", "categoria": "Mercearia",
            "preco_compra": 6, "preco_venda": 9, "estoque": 1,
        }).get_json()["id"]
        response = self.client.post("/api/vendas/lote", json={
            "itens": [{"id": p1, "qtd": 2}, {"id": p2, "qtd": 2}]
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.obter_produto(p1)["estoque"], 5)
        self.assertEqual(self.obter_produto(p2)["estoque"], 1)
        self.assertEqual(self.client.get("/api/vendas").get_json(), [])

    def test_produto_rejeita_estoque_fracionario_e_preco_infinito(self):
        payload = {"produto": "Leite", "categoria": "Bebidas",
                   "preco_compra": 2, "preco_venda": 3, "estoque": 1.5}
        self.assertEqual(self.client.post("/api/produtos", json=payload).status_code, 400)
        payload["estoque"] = 2
        payload["preco_venda"] = float("inf")
        self.assertEqual(self.client.post("/api/produtos", json=payload).status_code, 400)

    def test_endpoint_venda_simples_valida_quantidade(self):
        produto_id = self.criar_produto(3)
        response = self.client.post("/api/vendas", json={
            "produto_id": produto_id, "quantidade": 1
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["produto"], "Arroz")
        self.assertEqual(self.obter_produto(produto_id)["estoque"], 2)

    def test_estatisticas_devolve_ate_30_datas_em_ordem(self):
        # O teste cobre a estrutura/ordenação da resposta; datas históricas são
        # inseridas diretamente para não depender do relógio do ambiente.
        produto_id = self.criar_produto(100)
        import sqlite3
        with sqlite3.connect(main.DB_PATH) as conn:
            for day in range(1, 36):
                date = f"2026-01-{day:02d}" if day <= 31 else f"2026-02-{day-31:02d}"
                conn.execute("""INSERT INTO transacoes
                    (produto_id,produto,quantidade,preco_unitario,custo_unitario,total,lucro,criado_em)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (produto_id, "Arroz", 1, 8, 5, 8, 3, date + " 12:00:00"))
        response = self.client.get("/api/estatisticas")
        self.assertEqual(response.status_code, 200)
        dates = [row["data"] for row in response.get_json()]
        self.assertLessEqual(len(dates), 30)
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(dates[-1], "2026-02-04")


if __name__ == "__main__":
    unittest.main()
