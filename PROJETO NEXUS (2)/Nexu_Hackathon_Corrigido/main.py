"""API e servidor do Nexu / Mercantil do Vizinho.

Servidor local para demonstração. Antes de expor na rede, implemente autenticação,
autorização, HTTPS e uma estratégia de backup adequada.
"""
from pathlib import Path
from contextlib import contextmanager
import math
import os
import sqlite3

from flask import Flask, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("NEXU_DB_PATH", BASE_DIR / "database.db")).resolve()
app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # evita payloads excessivos


@contextmanager
def conectar():
    """Abre uma conexão e garante commit/rollback e fechamento."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inicializar_banco():
    with conectar() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, produto TEXT NOT NULL,
            preco_compra REAL NOT NULL DEFAULT 0, preco_venda REAL NOT NULL DEFAULT 0,
            estoque INTEGER NOT NULL DEFAULT 0, categoria TEXT NOT NULL DEFAULT 'Geral',
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        colunas = {row[1] for row in conn.execute("PRAGMA table_info(vendas)")}
        for nome, definicao in (
            ("estoque", "INTEGER NOT NULL DEFAULT 0"),
            ("categoria", "TEXT NOT NULL DEFAULT 'Geral'"),
            ("criado_em", "TEXT"),
        ):
            if nome not in colunas:
                conn.execute(f"ALTER TABLE vendas ADD COLUMN {nome} {definicao}")
        conn.execute("""CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INTEGER, produto TEXT NOT NULL,
            quantidade INTEGER NOT NULL, preco_unitario REAL NOT NULL, custo_unitario REAL NOT NULL,
            total REAL NOT NULL, lucro REAL NOT NULL, criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(produto_id) REFERENCES vendas(id) ON DELETE SET NULL)""")
        # Mantém o comportamento previsível em uso local e ajuda a serializar escritas.
        conn.execute("PRAGMA journal_mode = WAL")


inicializar_banco()


def erro(mensagem, status=400):
    return jsonify({"erro": mensagem}), status


def inteiro_positivo(valor, *, maximo=1_000_000):
    """Aceita apenas inteiros positivos reais; rejeita bool, float fracionário e strings inválidas."""
    if isinstance(valor, bool):
        raise ValueError
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and valor.strip().isdigit():
        numero = int(valor.strip())
    else:
        raise ValueError
    if numero < 1 or numero > maximo:
        raise ValueError
    return numero


def validar_produto(dados):
    if not isinstance(dados, dict):
        return None, "Envie os dados do produto em formato JSON."
    nome = str(dados.get("produto", "")).strip()
    categoria = str(dados.get("categoria", "Geral")).strip() or "Geral"
    if not nome or len(nome) > 100:
        return None, "O nome deve ter entre 1 e 100 caracteres."
    if len(categoria) > 60:
        return None, "A categoria deve ter até 60 caracteres."

    def parse_price(valor):
        if isinstance(valor, bool) or valor is None:
            raise ValueError
        if isinstance(valor, str):
            valor = valor.strip().replace(",", ".")
            if not valor:
                raise ValueError
        numero = float(valor)
        if not math.isfinite(numero) or numero < 0 or numero > 1_000_000_000:
            raise ValueError
        return round(numero, 2)

    try:
        compra = parse_price(dados.get("preco_compra"))
        venda = parse_price(dados.get("preco_venda"))
        estoque_raw = dados.get("estoque", 0)
        if isinstance(estoque_raw, bool):
            raise ValueError
        if isinstance(estoque_raw, int):
            estoque = estoque_raw
        elif isinstance(estoque_raw, str) and estoque_raw.strip().isdigit():
            estoque = int(estoque_raw.strip())
        else:
            raise ValueError
        if estoque < 0 or estoque > 1_000_000:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return None, "Informe preços não negativos e um estoque inteiro válido."

    return (nome, compra, venda, estoque, categoria), None


@app.errorhandler(413)
def payload_muito_grande(_exc):
    return erro("A requisição excede o limite de 1 MB.", 413)


@app.get("/")
def inicio():
    return app.send_static_file("index.html")


@app.get("/api/produtos")
@app.get("/vendas")
def listar_produtos():
    termo = request.args.get("busca", "").strip()
    with conectar() as conn:
        rows = conn.execute("""SELECT id, produto, preco_compra, preco_venda, estoque, categoria, criado_em FROM vendas
            WHERE produto LIKE ? OR categoria LIKE ? ORDER BY produto COLLATE NOCASE""",
            (f"%{termo}%", f"%{termo}%")).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/produtos")
@app.post("/vendas")
def criar_produto():
    valores, problema = validar_produto(request.get_json(silent=True))
    if problema:
        return erro(problema)
    with conectar() as conn:
        cur = conn.execute(
            "INSERT INTO vendas(produto,preco_compra,preco_venda,estoque,categoria) VALUES(?,?,?,?,?)",
            valores,
        )
        row = conn.execute("SELECT * FROM vendas WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/produtos/<int:produto_id>", methods=["PUT", "DELETE"])
@app.route("/vendas/<int:produto_id>", methods=["PUT", "DELETE"])
def produto_individual(produto_id):
    if request.method == "DELETE":
        with conectar() as conn:
            cur = conn.execute("DELETE FROM vendas WHERE id=?", (produto_id,))
        return ("", 204) if cur.rowcount else erro("Produto não encontrado.", 404)

    valores, problema = validar_produto(request.get_json(silent=True))
    if problema:
        return erro(problema)
    with conectar() as conn:
        cur = conn.execute(
            "UPDATE vendas SET produto=?,preco_compra=?,preco_venda=?,estoque=?,categoria=? WHERE id=?",
            (*valores, produto_id),
        )
        row = conn.execute("SELECT * FROM vendas WHERE id=?", (produto_id,)).fetchone()
    return (jsonify(dict(row)), 200) if cur.rowcount else erro("Produto não encontrado.", 404)


def normalizar_itens_venda(dados):
    """Valida e consolida itens repetidos para não vender além do estoque."""
    if not isinstance(dados, dict):
        raise ValueError("Envie os dados da venda em formato JSON.")
    itens = dados.get("itens")
    if not isinstance(itens, list) or not itens:
        raise ValueError("Envie a lista de itens do carrinho no formato JSON.")
    if len(itens) > 500:
        raise ValueError("A venda não pode conter mais de 500 itens.")

    consolidados = {}
    for item in itens:
        if not isinstance(item, dict):
            raise ValueError("Há um item inválido no carrinho.")
        try:
            produto_id = inteiro_positivo(item.get("id"))
            qtd = inteiro_positivo(item.get("qtd"))
        except ValueError:
            raise ValueError("Cada item deve conter um ID e uma quantidade inteira positiva.")
        consolidados[produto_id] = consolidados.get(produto_id, 0) + qtd
        if consolidados[produto_id] > 1_000_000:
            raise ValueError("A quantidade total de um produto excede o limite permitido.")
    return consolidados


def processar_venda(itens_por_id):
    """Executa validação, baixa de estoque e gravação dentro de uma transação exclusiva."""
    with conectar() as conn:
        # Obtém o bloqueio de escrita antes de ler o estoque, evitando duas vendas concorrentes
        # validarem simultaneamente o mesmo saldo.
        conn.execute("BEGIN IMMEDIATE")
        preparados = []
        for produto_id, qtd in itens_por_id.items():
            produto = conn.execute("SELECT * FROM vendas WHERE id=?", (produto_id,)).fetchone()
            if not produto:
                raise LookupError(f"Produto de ID {produto_id} não encontrado.")
            if produto["estoque"] < qtd:
                raise StockError(
                    f"Estoque insuficiente para {produto['produto']}. Disponível: {produto['estoque']}."
                )
            total = round(float(produto["preco_venda"]) * qtd, 2)
            lucro = round((float(produto["preco_venda"]) - float(produto["preco_compra"])) * qtd, 2)
            preparados.append((produto, qtd, total, lucro))

        # Condição adicional de estoque como defesa em profundidade.
        detalhes = []
        for produto, qtd, total, lucro in preparados:
            cur = conn.execute(
                "UPDATE vendas SET estoque=estoque-? WHERE id=? AND estoque>=?",
                (qtd, produto["id"], qtd),
            )
            if cur.rowcount != 1:
                raise StockError(f"Estoque insuficiente para {produto['produto']}.")
            cur = conn.execute(
                """INSERT INTO transacoes
                   (produto_id,produto,quantidade,preco_unitario,custo_unitario,total,lucro)
                   VALUES(?,?,?,?,?,?,?)""",
                (produto["id"], produto["produto"], qtd, produto["preco_venda"],
                 produto["preco_compra"], total, lucro),
            )
            # Guarda o ID gerado nesta transação, sem consultar "a última venda" depois do commit.
            detalhes.append({
                "id": cur.lastrowid, "produto_id": produto["id"], "produto": produto["produto"],
                "quantidade": qtd, "total": total, "lucro": lucro,
            })
        return sum(item[2] for item in preparados), sum(item[3] for item in preparados), detalhes


class StockError(Exception):
    pass


@app.post("/api/vendas/lote")
def registrar_venda_lote():
    try:
        itens = normalizar_itens_venda(request.get_json(silent=True))
        total, lucro, _detalhes = processar_venda(itens)
        return jsonify({
            "mensagem": "Venda em lote concluída com sucesso!",
            "itens": len(itens),
            "total": round(total, 2),
            "lucro": round(lucro, 2),
        }), 201
    except ValueError as exc:
        return erro(str(exc), 400)
    except LookupError as exc:
        return erro(str(exc), 404)
    except StockError as exc:
        return erro(str(exc), 400)
    except sqlite3.Error:
        app.logger.exception("Falha ao registrar venda em lote")
        return erro("Não foi possível registrar a venda devido a um erro no banco de dados.", 500)


@app.post("/api/vendas")
def registrar_venda():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return erro("Envie os dados da venda em formato JSON.")
    try:
        produto_id = inteiro_positivo(dados.get("produto_id"))
        quantidade = inteiro_positivo(dados.get("quantidade"))
        total, lucro, detalhes = processar_venda({produto_id: quantidade})
        detalhe = detalhes[0]
        return jsonify({
            "id": detalhe["id"], "produto": detalhe["produto"],
            "quantidade": quantidade, "total": round(total, 2), "lucro": round(lucro, 2),
        }), 201
    except ValueError:
        return erro("Selecione um produto e informe uma quantidade inteira positiva.")
    except LookupError as exc:
        return erro(str(exc), 404)
    except StockError as exc:
        return erro(str(exc), 400)
    except sqlite3.Error:
        app.logger.exception("Falha ao registrar venda")
        return erro("Não foi possível registrar a venda devido a um erro no banco de dados.", 500)


@app.get("/api/vendas")
def historico_vendas():
    with conectar() as conn:
        rows = conn.execute("SELECT * FROM transacoes ORDER BY criado_em DESC, id DESC LIMIT 100").fetchall()
    return jsonify([dict(row) for row in rows])


@app.get("/api/estatisticas")
def estatisticas_vendas():
    with conectar() as conn:
        # Busca as 30 datas mais recentes e devolve em ordem cronológica para o gráfico.
        rows = conn.execute("""
            SELECT data, total FROM (
                SELECT DATE(criado_em) AS data, SUM(total) AS total
                FROM transacoes
                GROUP BY DATE(criado_em)
                ORDER BY data DESC
                LIMIT 30
            )
            ORDER BY data ASC
        """).fetchall()
    return jsonify([dict(row) for row in rows])


@app.get("/api/analytics")
def get_analytics():
    with conectar() as conn:
        top_produtos = conn.execute("""
            SELECT produto, SUM(quantidade) AS total_qtd, SUM(total) AS faturamento
            FROM transacoes
            GROUP BY produto
            ORDER BY total_qtd DESC
            LIMIT 5
        """).fetchall()
        estoque_critico = conn.execute("""
            SELECT produto, estoque FROM vendas
            WHERE estoque <= 5
            ORDER BY estoque ASC, produto COLLATE NOCASE
        """).fetchall()
    return jsonify({
        "top_produtos": [dict(r) for r in top_produtos],
        "estoque_critico": [dict(r) for r in estoque_critico],
    })


@app.get("/api/resumo")
@app.get("/resumo")
def resumo():
    with conectar() as conn:
        produtos = conn.execute("""
            SELECT COUNT(*) AS quantidade,
                   COALESCE(SUM(preco_compra*estoque),0) AS investido,
                   COALESCE(SUM(CASE WHEN estoque<=5 THEN 1 ELSE 0 END),0) AS baixo_estoque
            FROM vendas
        """).fetchone()
        vendas = conn.execute("""
            SELECT COUNT(*) AS transacoes, COALESCE(SUM(total),0) AS faturamento,
                   COALESCE(SUM(lucro),0) AS lucro FROM transacoes
        """).fetchone()
    return jsonify({**dict(produtos), **dict(vendas)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
