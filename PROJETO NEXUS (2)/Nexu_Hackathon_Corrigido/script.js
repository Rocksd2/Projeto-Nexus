const $ = (id) => document.getElementById(id);
const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const LIMITE_ESTOQUE = 5;
let catalogo = [];
let avisoTimer;
let chartInstance = null;
let carrinho = lerCarrinho();

/* ---------- utilitários ---------- */
function el(tag, cls, txt) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt !== undefined) e.textContent = txt; // textContent evita XSS
  return e;
}
const porId = (id) => catalogo.find((p) => String(p.id) === String(id));
const dataBR = (s) => {
  const iso = /(Z|[+-]\d{2}:?\d{2})$/i.test(s) ? s : `${String(s).replace(" ", "T")}Z`;
  const d = new Date(iso);
  return isNaN(d) ? String(s) : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
};

function lerCarrinho() {
  try {
    const c = JSON.parse(localStorage.getItem("nexu_cart") || "[]");
    return Array.isArray(c) ? c : [];
  } catch { return []; }
}

async function api(url, options = {}) {
  const headers = options.body ? { "Content-Type": "application/json", ...(options.headers || {}) } : options.headers;
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.erro || `Não foi possível concluir a operação (${response.status}).`);
  }
  return response.status === 204 ? null : response.json();
}

function notificar(mensagem, tipo = "success") {
  const n = $("aviso");
  n.textContent = mensagem; n.className = `notice ${tipo}`; n.hidden = false;
  clearTimeout(avisoTimer);
  avisoTimer = setTimeout(() => { n.hidden = true; }, 4200);
}

function setButtonLoading(btn, on) {
  if (on) { btn.dataset.html = btn.innerHTML; btn.innerHTML = "<span>⌛ Carregando...</span>"; }
  else if (btn.dataset.html !== undefined) btn.innerHTML = btn.dataset.html;
  btn.disabled = on;
}

function atualizarData() {
  const d = new Date();
  const dia = d.toLocaleDateString("pt-BR", { weekday: "long" });
  const data = d.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
  $("eyebrow").textContent = `${dia}, ${data}`.toUpperCase();
}

function itemLinha(titulo, sub, direita) {
  const row = el("div", "history-item");
  const info = el("div");
  info.append(el("strong", "", titulo), el("small", "", sub));
  row.append(info, direita);
  return row;
}

/* ---------- analytics ---------- */
async function carregarAnalytics() {
  try {
    const r = await api("/api/analytics");
    const top = $("top-produtos-lista"); top.replaceChildren();
    if (!r.top_produtos.length) top.append(el("p", "history-empty", "Sem dados suficientes."));
    r.top_produtos.forEach((p, i) => top.append(
      itemLinha(`${i + 1}º ${p.produto}`, `${p.total_qtd} un. vendidas`, el("strong", "history-total", moeda.format(p.faturamento)))));
    const crit = $("estoque-critico-lista"); crit.replaceChildren();
    if (!r.estoque_critico.length) crit.append(el("p", "history-empty", "Estoque saudável!"));
    r.estoque_critico.forEach((p) => crit.append(
      itemLinha(p.produto, `Apenas ${p.estoque} un. restantes`, el("span", "stock-pill low", `${p.estoque} un.`))));
  } catch (e) { console.error("Erro analytics:", e); }
}

/* ---------- carrinho ---------- */
function salvarCarrinho() { localStorage.setItem("nexu_cart", JSON.stringify(carrinho)); }

function botaoCarrinho(txt, acao, i, rotulo, extra = "") {
  const b = el("button", `icon-button qty ${extra}`.trim(), txt);
  b.type = "button"; b.dataset.acao = acao; b.dataset.i = i; b.setAttribute("aria-label", rotulo);
  return b;
}

function atualizarCarrinho() {
  const lista = $("cart-items"); lista.replaceChildren();
  let total = 0;
  if (!carrinho.length) lista.append(el("p", "history-empty", "Carrinho vazio."));
  carrinho.forEach((it, i) => {
    total += it.preco * it.qtd;
    const acoes = el("div", "cart-actions");
    acoes.append(
      el("strong", "", moeda.format(it.preco * it.qtd)),
      botaoCarrinho("−", "dec", i, `Diminuir ${it.nome}`),
      botaoCarrinho("+", "inc", i, `Aumentar ${it.nome}`),
      botaoCarrinho("×", "rem", i, `Remover ${it.nome}`, "danger"));
    lista.append(itemLinha(it.nome, `${it.qtd}x ${moeda.format(it.preco)}`, acoes));
  });
  $("previa-total").textContent = moeda.format(total);
  salvarCarrinho();
}

// Revalida o carrinho salvo com o estoque e os preços atuais
function sanearCarrinho() {
  const antes = JSON.stringify(carrinho);
  carrinho = carrinho.map((it) => {
    const p = porId(it.id);
    const qtd = Math.min(Math.trunc(Number(it.qtd)) || 0, p ? p.estoque : 0);
    return p && qtd >= 1 ? { id: p.id, nome: p.produto, preco: p.preco_venda, qtd } : null;
  }).filter(Boolean);
  if (JSON.stringify(carrinho) !== antes) notificar("Carrinho ajustado ao estoque e aos preços atuais.", "error");
  atualizarCarrinho();
}

function adicionarAoCarrinho() {
  const valor = $("venda-produto").value;
  if (!valor) return notificar("Selecione um produto!", "error");
  const produto = porId(valor);
  if (!produto) return notificar("Produto não encontrado. Atualize a página.", "error");
  if (produto.estoque < 1) return notificar("Produto esgotado!", "error");
  const existe = carrinho.find((i) => String(i.id) === String(produto.id));
  if (existe) {
    if (existe.qtd + 1 > produto.estoque) return notificar("Estoque insuficiente!", "error");
    existe.qtd++;
  } else {
    carrinho.push({ id: produto.id, nome: produto.produto, preco: produto.preco_venda, qtd: 1 });
  }
  atualizarCarrinho();
}

$("cart-items").addEventListener("click", (e) => {
  const b = e.target.closest("[data-acao]"); if (!b) return;
  const i = Number(b.dataset.i); const it = carrinho[i]; if (!it) return;
  if (b.dataset.acao === "rem") carrinho.splice(i, 1);
  else if (b.dataset.acao === "dec") { it.qtd--; if (it.qtd < 1) carrinho.splice(i, 1); }
  else {
    const p = porId(it.id);
    if (p && it.qtd >= p.estoque) return notificar("Estoque insuficiente!", "error");
    it.qtd++;
  }
  atualizarCarrinho();
});

async function finalizarVenda() {
  if (!carrinho.length) return notificar("O carrinho está vazio!", "error");
  const btn = $("finish-sale");
  setButtonLoading(btn, true);
  try {
    // O servidor deve recalcular preço/lucro e validar o estoque pelo id; não confie no preço enviado.
    await api("/api/vendas/lote", { method: "POST", body: JSON.stringify({ itens: carrinho }) });
    notificar("Venda concluída com sucesso!");
    carrinho = [];
    atualizarCarrinho();
    await atualizarTudo();
  } catch (e) {
    notificar("Erro ao processar venda: " + e.message, "error");
  } finally { setButtonLoading(btn, false); }
}

/* ---------- produtos ---------- */
function renderProdutos() {
  const termo = $("busca").value.trim().toLocaleLowerCase("pt-BR");
  const lista = catalogo.filter((p) => `${p.produto} ${p.categoria}`.toLocaleLowerCase("pt-BR").includes(termo));
  const corpo = $("lista"); corpo.replaceChildren();
  $("vazio").hidden = lista.length > 0;
  lista.forEach((p) => {
    const tr = document.createElement("tr");
    const nome = el("td", "product-name");
    nome.append(el("span", "product-badge", p.produto.slice(0, 1).toUpperCase()), el("span", "", p.produto));
    const cat = el("td"); cat.append(el("span", "category-pill", p.categoria));
    const est = el("td"); est.append(el("span", `stock-pill ${p.estoque <= LIMITE_ESTOQUE ? "low" : "ok"}`, `${p.estoque} un.`));
    // Margem sobre a venda: (venda - custo) / venda
    const margem = p.preco_venda > 0 ? ((p.preco_venda - p.preco_compra) / p.preco_venda) * 100 : null;
    const mg = el("td", p.preco_venda >= p.preco_compra ? "margin-positive" : "margin-negative", margem === null ? "—" : `${margem.toFixed(0)}%`);
    const acoes = el("td", "row-actions");
    const ed = el("button", "icon-button", "✎"); ed.type = "button"; ed.title = "Editar produto"; ed.setAttribute("aria-label", `Editar ${p.produto}`); ed.onclick = () => abrirProduto(p);
    const del = el("button", "icon-button danger", "×"); del.type = "button"; del.title = "Excluir produto"; del.setAttribute("aria-label", `Excluir ${p.produto}`); del.onclick = () => excluirProduto(p);
    acoes.append(ed, del);
    tr.append(nome, cat, el("td", "", moeda.format(p.preco_compra)), el("td", "price-sale", moeda.format(p.preco_venda)), est, mg, acoes);
    corpo.append(tr);
  });
}

function preencherSeletor() {
  const sel = $("venda-produto"); const atual = sel.value;
  sel.replaceChildren(new Option("Selecione um produto", ""));
  catalogo.forEach((p) => {
    const opt = new Option(`${p.produto} · ${p.estoque} un. · ${moeda.format(p.preco_venda)}`, p.id);
    opt.disabled = p.estoque < 1; sel.add(opt);
  });
  if ([...sel.options].some((o) => o.value === atual)) sel.value = atual;
}

async function carregarProdutos() {
  catalogo = await api("/api/produtos");
  renderProdutos(); preencherSeletor(); sanearCarrinho();
}

/* ---------- resumo, histórico, gráfico ---------- */
async function carregarResumo() {
  const r = await api("/api/resumo");
  $("total_produtos").textContent = r.quantidade;
  $("total_investido").textContent = moeda.format(r.investido);
  $("total_vendas").textContent = moeda.format(r.faturamento);
  $("total_transacoes").textContent = r.transacoes;
  $("lucro_total").textContent = moeda.format(r.lucro);
  $("lucro_total").classList.toggle("negative", r.lucro < 0);
}

async function carregarHistorico() {
  const itens = await api("/api/vendas");
  const lista = $("historico-lista"); lista.replaceChildren();
  $("historico-count").textContent = itens.length;
  if (!itens.length) { lista.append(el("p", "history-empty", "As vendas registradas aparecerão aqui.")); return; }
  itens.slice(0, 6).forEach((v) => lista.append(
    itemLinha(v.produto, `${v.quantidade} un. · ${dataBR(v.criado_em)}`, el("strong", "history-total", moeda.format(v.total)))));
}

async function carregarGrafico() {
  try {
    if (typeof Chart === "undefined") throw new Error("Chart.js não carregou");
    const dados = await api("/api/estatisticas");
    $("grafico-erro").hidden = true;
    const rotulo = (s) => { const p = String(s).split("-"); return p.length === 3 ? `${p[2]}/${p[1]}` : s; };
    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart($("chartVendas").getContext("2d"), {
      type: "line",
      data: { labels: dados.map((d) => rotulo(d.data)), datasets: [{ label: "Faturamento", data: dados.map((d) => d.total), borderColor: "#a4d65e", backgroundColor: "#a4d65e33", fill: true, tension: 0.4, pointRadius: 4 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => moeda.format(c.parsed.y) } } },
        scales: { x: { grid: { display: false }, ticks: { color: "#8d9a8f" } }, y: { grid: { color: "#28352b" }, ticks: { color: "#8d9a8f", callback: (v) => moeda.format(v) } } }
      }
    });
  } catch (e) { console.error("Erro gráfico:", e); $("grafico-erro").hidden = false; }
}

async function atualizarTudo() {
  await Promise.all([carregarProdutos(), carregarResumo(), carregarHistorico(), carregarGrafico(), carregarAnalytics()]);
}

/* ---------- diálogo de produto ---------- */
function abrirProduto(p = null) {
  $("form-produto").reset(); $("produto-id").value = p?.id || "";
  $("dialog-titulo").textContent = p ? "Editar produto" : "Novo produto";
  $("produto").value = p?.produto || ""; $("categoria").value = p?.categoria || "Geral";
  $("compra").value = p?.preco_compra ?? ""; $("venda").value = p?.preco_venda ?? ""; $("estoque").value = p?.estoque ?? 0;
  $("produto-dialog").showModal(); $("produto").focus();
}

async function excluirProduto(p) {
  if (!confirm(`Excluir “${p.produto}” do catálogo?`)) return;
  try { await api(`/api/produtos/${p.id}`, { method: "DELETE" }); notificar("Produto excluído."); await atualizarTudo(); }
  catch (e) { notificar(e.message, "error"); }
}

$("form-produto").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const id = $("produto-id").value;
  const btn = ev.target.querySelector("button[type='submit']");
  const dados = {
    produto: $("produto").value.trim(),
    categoria: $("categoria").value.trim() || "Geral",
    preco_compra: Number($("compra").value),
    preco_venda: Number($("venda").value),
    estoque: Math.trunc(Number($("estoque").value))
  };
  const numeros = [dados.preco_compra, dados.preco_venda, dados.estoque];
  if (!dados.produto || !numeros.every((n) => Number.isFinite(n) && n >= 0))
    return notificar("Preencha o nome e use valores numéricos não negativos.", "error");
  setButtonLoading(btn, true);
  try {
    await api(id ? `/api/produtos/${id}` : "/api/produtos", { method: id ? "PUT" : "POST", body: JSON.stringify(dados) });
    $("produto-dialog").close();
    notificar(id ? "Produto atualizado." : "Produto cadastrado.");
    await atualizarTudo();
  } catch (e) { notificar(e.message, "error"); }
  finally { setButtonLoading(btn, false); }
});

/* ---------- exportar CSV ---------- */
// Neutraliza fórmulas (=,+,-,@) e escapa ; e aspas nos campos de texto
const csvTexto = (v) => {
  let s = String(v ?? "");
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[;"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
const csvNum = (n) => String(n ?? "").replace(".", ",");

$("exportar-csv").addEventListener("click", async () => {
  try {
    const v = await api("/api/vendas");
    const linhas = v.map((i) => [i.id, csvTexto(i.produto), i.quantidade, csvNum(i.total), csvNum(i.lucro), csvTexto(i.criado_em)].join(";"));
    const csv = "\uFEFF" + ["ID;Produto;Qtd;Total;Lucro;Data", ...linhas].join("\r\n"); // BOM: acentos corretos no Excel
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = "vendas_nexu.csv";
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { notificar(e.message, "error"); }
});

/* ---------- eventos gerais ---------- */
$("novo-produto").addEventListener("click", () => abrirProduto());
$("fechar-dialog").addEventListener("click", () => $("produto-dialog").close());
$("cancelar-dialog").addEventListener("click", () => $("produto-dialog").close());
let buscaTimer;
$("busca").addEventListener("input", () => { clearTimeout(buscaTimer); buscaTimer = setTimeout(renderProdutos, 200); }); // filtra localmente
$("add-cart").addEventListener("click", adicionarAoCarrinho);
$("finish-sale").addEventListener("click", finalizarVenda);

/* ---------- item ativo do menu ---------- */
const navObs = new IntersectionObserver((entradas) => entradas.forEach((e) => {
  if (!e.isIntersecting) return;
  document.querySelectorAll(".nav-link").forEach((a) => {
    const ativo = a.getAttribute("href") === e.target.dataset.nav;
    a.classList.toggle("active", ativo);
    if (ativo) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}), { rootMargin: "-30% 0px -60% 0px" });
[[".topbar, .stats, .analytics-grid, #grafico-panel", "#inicio"], ["#produtos", "#produtos"], ["#caixa", "#caixa"], ["#historico", "#historico"]]
  .forEach(([sel, href]) => document.querySelectorAll(sel).forEach((n) => { n.dataset.nav = href; navObs.observe(n); }));

/* ---------- início ---------- */
atualizarData(); setInterval(atualizarData, 60000);
atualizarCarrinho();
atualizarTudo().catch((e) => notificar(`Erro ao conectar: ${e.message}`, "error"));