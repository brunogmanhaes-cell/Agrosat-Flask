// AgroSat - front-end. Toda a regra de decisão fica no Python; aqui só há interface.

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const PLACEHOLDER = '<div class="empty">Escolha uma plantação e toque em <b>Gerar recomendação</b>.</div>';

let plantacoes = [], editando = null, selecionada = null;

async function api(url, opcoes = {}) {
  let resposta;
  try {
    resposta = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opcoes });
  } catch (e) {
    throw new Error("Não foi possível falar com o servidor do AgroSat.");
  }
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(dados.erro || "Erro inesperado.");
  return dados;
}

// ---------- Plantações ----------

async function carregar() {
  try {
    plantacoes = await api("/api/plantacoes");
    renderLista();
  } catch (e) {
    $("lista").innerHTML = `<p class="err" role="alert">${esc(e.message)}</p>`;
  }
}

function renderLista() {
  if (!plantacoes.length) {
    $("lista").innerHTML = '<div class="empty">Nenhuma plantação ainda. Cadastre a primeira acima.</div>';
    return;
  }
  $("lista").innerHTML = plantacoes.map(p => `
    <div class="farm ${p.id_plantacao === selecionada ? "sel" : ""}" data-id="${p.id_plantacao}">
      <h3>${esc(p.nome_fazenda)}</h3>
      <small>${esc(p.produtor)} · ${p.latitude}, ${p.longitude}</small>
      <span class="tag">${p.tipo_solo ? esc(p.tipo_solo) : "Solo ainda não identificado"}</span>
      <div class="actions">
        <button class="primary" data-a="rec">Gerar recomendação</button>
        <button data-a="ed">Editar</button>
        <button class="danger" data-a="del">Excluir</button>
      </div>
    </div>`).join("");
}

async function salvar() {
  const corpo = {
    produtor: $("f-prod").value, nome_fazenda: $("f-faz").value,
    latitude: $("f-lat").value, longitude: $("f-lon").value
  };
  try {
    if (editando) await api(`/api/plantacoes/${editando}`, { method: "PUT", body: JSON.stringify(corpo) });
    else await api("/api/plantacoes", { method: "POST", body: JSON.stringify(corpo) });
    cancelarEdicao();
    await carregar();
  } catch (e) {
    $("f-err").textContent = e.message;
  }
}

function cancelarEdicao() {
  editando = null;
  ["f-prod", "f-faz", "f-lat", "f-lon"].forEach(i => $(i).value = "");
  $("f-prod").disabled = false;
  $("tit-form").textContent = "Nova plantação";
  $("f-cancelar").hidden = true;
  $("f-err").textContent = "";
}

function editar(id) {
  const p = plantacoes.find(x => x.id_plantacao === id);
  editando = id;
  $("f-prod").value = p.produtor; $("f-prod").disabled = true; // o produtor não muda aqui
  $("f-faz").value = p.nome_fazenda; $("f-lat").value = p.latitude; $("f-lon").value = p.longitude;
  $("tit-form").textContent = "Editar plantação";
  $("f-cancelar").hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function excluir(id) {
  const p = plantacoes.find(x => x.id_plantacao === id);
  if (!confirm(`Apagar a plantação ${p.nome_fazenda} e seu histórico?`)) return;
  try {
    await api(`/api/plantacoes/${id}`, { method: "DELETE" });
    if (selecionada === id) {
      selecionada = null; $("historico").hidden = true; $("resultado").innerHTML = PLACEHOLDER;
    }
    await carregar();
  } catch (e) {
    alert(e.message);
  }
}

// ---------- Recomendação ----------

async function gerar(id) {
  selecionada = id; renderLista();
  const caixa = $("resultado");
  caixa.innerHTML = '<div class="spin">Consultando solo, previsão e umidade. Pode levar alguns segundos…</div>';
  try {
    const r = await api(`/api/plantacoes/${id}/recomendacao`, { method: "POST" });
    const p = plantacoes.find(x => x.id_plantacao === id);
    desenhar(p, r);
    await carregar();           // atualiza a etiqueta do solo
    await carregarHistorico(id);
  } catch (e) {
    caixa.innerHTML = `<p class="err" role="alert"><b>Não foi possível gerar a recomendação.</b><br>${esc(e.message)}</p>`;
  }
}

function desenhar(p, r) {
  const { solo, clima } = r;
  const cc = solo.capacidade_campo, pmp = solo.ponto_murcha, ESCALA = 0.5;
  const pct = v => Math.min(100, v / ESCALA * 100);
  const cls = r.decisao === "REGAR" ? "c-regar" : r.decisao === "AGUARDAR" ? "c-aguardar" : "c-nao";
  const maxMm = Math.max(10, ...clima.previsao_diaria.map(d => d.chuva_mm));
  const composicao = solo.argila == null ? "Textura salva no banco"
    : `Argila ${solo.argila.toFixed(0)}% · areia ${solo.areia.toFixed(0)}% · silte ${solo.silte.toFixed(0)}%`;

  $("resultado").innerHTML = `
    <h2>${esc(p.nome_fazenda)}</h2>
    <div class="verdict">
      <div class="tank" role="img" aria-label="Umidade do solo ${(clima.umidade_solo * 100).toFixed(1)}%, entre ponto de murcha ${(pmp * 100).toFixed(0)}% e capacidade de campo ${(cc * 100).toFixed(0)}%">
        <div class="fill" id="fill" style="height:0"></div>
        <div class="mark" style="bottom:${pct(cc)}%"><span>campo ${(cc * 100).toFixed(0)}%</span></div>
        <div class="mark" style="bottom:${pct(pmp)}%"><span>murcha ${(pmp * 100).toFixed(0)}%</span></div>
      </div>
      <div>
        <div class="badge ${cls}">${esc(r.decisao)}</div>
        <p class="motivo">${esc(r.motivo)}</p>
        ${r.alertas.map(a => `<div class="alerta">${esc(a)}</div>`).join("")}
      </div>
    </div>
    <div class="stats">
      <div class="stat"><b>${(clima.umidade_solo * 100).toFixed(1)}%</b><span>Umidade atual (0 a 81 cm)</span></div>
      <div class="stat"><b>${r.agua_disponivel.toFixed(0)}%</b><span>Água disponível para a planta</span></div>
      <div class="stat"><b>${clima.chuva_total_mm.toFixed(1)} mm</b><span>Chuva em 3 dias</span></div>
      <div class="stat"><b>${esc(solo.tipo)}</b><span>${composicao}</span></div>
    </div>
    <h2 style="margin-top:20px">Previsão de chuva</h2>
    <div class="days">${clima.previsao_diaria.map(d => `
      <div class="day"><span>${d.prob}%</span><i style="height:0" data-h="${d.chuva_mm / maxMm * 80}%"></i><b>${d.chuva_mm.toFixed(1)} mm</b><span>${d.data.slice(8)}/${d.data.slice(5, 7)}</span></div>`).join("")}
    </div>`;

  // Dois frames de espera para a animação de subida da água rodar
  requestAnimationFrame(() => requestAnimationFrame(() => {
    $("fill").style.height = pct(clima.umidade_solo) + "%";
    document.querySelectorAll(".day i").forEach(i => i.style.height = i.dataset.h);
  }));
}

// ---------- Histórico ----------

async function carregarHistorico(id) {
  const caixa = $("historico");
  try {
    const { itens, contagem } = await api(`/api/plantacoes/${id}/historico`);
    if (!itens.length) { caixa.hidden = true; return; }
    caixa.hidden = false;
    caixa.innerHTML = `<h2>Histórico</h2>
      <p class="resumo">Irrigações desnecessárias evitadas: <b>${contagem["NÃO REGAR"] || 0}</b>
      · Regar: ${contagem["REGAR"] || 0} · Aguardar: ${contagem["AGUARDAR"] || 0}</p>
      <table><tr><th>Quando</th><th>Decisão</th><th>Motivo</th></tr>
      ${itens.map(i => `<tr>
        <td>${new Date(i.data_hora).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</td>
        <td><b>${esc(i.decisao)}</b></td><td>${esc(i.justificativa)}</td></tr>`).join("")}</table>`;
  } catch (e) {
    caixa.hidden = true;
  }
}

// ---------- Eventos ----------

$("f-salvar").onclick = salvar;
$("f-cancelar").onclick = cancelarEdicao;
$("lista").onclick = e => {
  const cartao = e.target.closest(".farm");
  if (!cartao) return;
  const id = +cartao.dataset.id, acao = e.target.dataset.a;
  if (acao === "rec") gerar(id);
  else if (acao === "ed") editar(id);
  else if (acao === "del") excluir(id);
  else { selecionada = id; renderLista(); carregarHistorico(id); }
};

carregar();
