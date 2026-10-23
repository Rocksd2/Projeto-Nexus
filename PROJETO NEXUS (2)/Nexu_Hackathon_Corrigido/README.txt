NEXU — MERCANTIL DO VIZINHO
Gestão de produtos, estoque e vendas
====================================

VERSÃO PARA HACKATHON — CORREÇÕES DE INTEGRIDADE
------------------------------------------------

PRINCIPAIS RECURSOS
- Cadastro, edição, pesquisa e exclusão de produtos.
- Controle de categorias, custo, preço de venda e estoque.
- Carrinho e registro de vendas.
- Baixa de estoque e histórico transacional.
- Indicadores de faturamento, lucro, estoque e produtos mais vendidos.
- Banco de dados local SQLite.

COMO INICIAR NO WINDOWS
-----------------------
1. Instale Python 3.9 ou superior e marque “Add Python to PATH”.
2. Dê duplo clique em start.bat.
3. Aguarde a instalação das dependências e o início do servidor.
4. Abra http://127.0.0.1:5000 no navegador.
5. Mantenha a janela do terminal aberta enquanto usa o sistema.

Se a instalação automática falhar, abra o terminal nesta pasta e execute:
  python -m venv .venv
  .venv\Scripts\activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  python main.py

COMO EXECUTAR OS TESTES
-----------------------
Com o ambiente virtual ativado e as dependências instaladas:
  python -m unittest discover -s tests -v

Os testes criam bancos temporários e não usam o database.db de demonstração.

API PRINCIPAL
-------------
  GET    /api/produtos?busca=termo     Lista/pesquisa produtos
  POST   /api/produtos                 Cria produto
  PUT    /api/produtos/<id>            Atualiza produto
  DELETE /api/produtos/<id>            Exclui produto
  POST   /api/vendas                   Registra uma venda
  POST   /api/vendas/lote              Registra os itens do carrinho
  GET    /api/vendas                   Lista até 100 vendas recentes
  GET    /api/estatisticas             Faturamento diário (até 30 dias)
  GET    /api/analytics                Produtos mais vendidos e estoque crítico
  GET    /api/resumo                   Indicadores do painel

EXEMPLOS DE JSON
----------------
Produto:
  {"produto":"Café", "categoria":"Mercearia", "preco_compra":10.50,
   "preco_venda":14.90, "estoque":20}

Venda simples:
  {"produto_id":1, "quantidade":2}

Venda em lote:
  {"itens":[{"id":1,"qtd":2},{"id":2,"qtd":1}]}

BANCO DE DADOS
--------------
O arquivo database.db incluído contém dados de demonstração do projeto. Faça
uma cópia antes de substituir ou limpar esse arquivo. O sistema cria as tabelas
necessárias ao iniciar e preserva a estrutura de um banco anterior compatível.

LIMITES IMPORTANTES
-------------------
- O servidor é vinculado a 127.0.0.1 e foi projetado para demonstração local.
- Não exponha o servidor diretamente à internet nem a uma rede compartilhada.
- Para produção, implemente autenticação/autorização, gestão segura de segredos,
  backups testados, auditoria, monitoramento e configuração de implantação.
- O Chart.js é carregado por CDN, então o gráfico pode não aparecer sem internet.
- Os valores financeiros são calculados em ponto flutuante; para uma implantação
  comercial de produção, avalie armazenar dinheiro como centavos inteiros ou
  usar Decimal de ponta a ponta.

ARQUIVOS
--------
  main.py       API Flask e regras de negócio
  index.html    Interface do sistema
  style.css     Estilos responsivos
  script.js     Interações com a API
  database.db   Banco local para demonstração
  tests/        Testes automatizados de regressão
  start.bat     Inicialização no Windows
