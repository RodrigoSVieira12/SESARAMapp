/* ==========================================================================
   Onde ir? Frontend (vanilla JS, sem frameworks). Versão 0.6.

   Fluxo de ecrãs:
     início > sinais de emergência (um toque) > escolha da queixa
     (lista OU pesquisa em texto livre) > perguntas em 3 fases >
     resultado (guia) > localização > encaminhamento (mapa)

   O backend é stateless: acumulamos as respostas em `estado.respostas`
   e reenviamos tudo em cada POST /api/triagem. Isso torna o "voltar
   atrás" trivial: apagamos a última resposta e voltamos a perguntar.

   Línguas: os textos do interface vivem em textos.js (PT e EN) e são
   escolhidos por t(chave). Os conteúdos clínicos vêm da API com campos
   *_en opcionais, escolhidos por campo(obj, nome) — se faltar o inglês,
   mostra-se o português. O botão PT/EN re-renderiza o ecrã atual
   (estado.renderAtual) sem perder as respostas dadas.

   Modo de demonstração: abrir a app com ?hora=2026-06-29T03:00:00 simula
   a hora do cálculo do encaminhamento.
   ========================================================================== */

"use strict";

const $app = document.getElementById("app");

const estado = {
  lingua: "pt",           // "pt" | "en" (definida no arranque, ver boot)
  queixa: null,
  respostas: {},          // {id_pergunta: "sim"|"nao"}: o que a API recebe
  historico: [],          // [{id, texto, resposta}]: para "voltar" e resumo
  resultado: null,
  unidades: null,         // cache para o fallback manual de localização
  mapa: null,             // instância Leaflet ativa (destruir ao re-renderizar)
  horaSimulada: new URLSearchParams(location.search).get("hora"),
  // {lat, lng, precisao (m|null), origem: "auto"|"concelho", rotulo}
  localizacao: null,
  renderAtual: null,      // função que redesenha o ecrã atual (troca de língua)
};

/* ----------------------------------------------------- língua e textos -- */

function t(chave, ...args) {
  const tabela = TEXTOS[estado.lingua] || TEXTOS.pt;
  let valor = tabela[chave];
  if (valor === undefined) valor = TEXTOS.pt[chave];
  return typeof valor === "function" ? valor(...args) : valor ?? chave;
}

/* Conteúdo clínico vindo da API: usa o campo *_en quando a língua é
   inglês e ele existe; caso contrário, o português (a omissão segura). */
function campo(obj, nome) {
  if (!obj) return "";
  if (estado.lingua === "en" && obj[nome + "_en"]) return obj[nome + "_en"];
  return obj[nome] ?? "";
}

function campoLista(obj, nome) {
  const valor = campo(obj, nome);
  return Array.isArray(valor) ? valor : [];
}

function linguaInicial() {
  const parametro = new URLSearchParams(location.search).get("lang");
  if (parametro === "en" || parametro === "pt") return parametro;
  try {
    const guardada = localStorage.getItem("ondeir.lingua");
    if (guardada === "en" || guardada === "pt") return guardada;
  } catch (_) { /* localStorage bloqueado: segue em PT */ }
  return "pt";
}

function aplicarLinguaEstatica() {
  document.documentElement.lang = estado.lingua;
  const sub = document.getElementById("topo-sub");
  if (sub) sub.textContent = t("topo_sub");
  const avisoRodape = document.getElementById("rodape-aviso");
  if (avisoRodape) avisoRodape.innerHTML = t("rodape_aviso");
  const notaRodape = document.getElementById("rodape-nota");
  if (notaRodape) notaRodape.innerHTML = t("rodape_nota");
  const botao = document.getElementById("btn-lingua");
  if (botao) {
    botao.textContent = estado.lingua === "pt" ? "EN" : "PT";
    botao.setAttribute("aria-label", t("lingua_aria"));
  }
}

/* ------------------------------------------------------------ helpers -- */

function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

async function api(caminho, corpo) {
  const opcoes = corpo
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      }
    : {};
  const resposta = await fetch(caminho, opcoes);
  if (!resposta.ok) {
    let detalhe = `Erro ${resposta.status}`;
    try {
      const json = await resposta.json();
      const d = json.detail;
      if (typeof d === "string") detalhe = d;
      else if (Array.isArray(d)) detalhe = d.map((e) => e.msg || "").join("; ");
    } catch (_) { /* corpo não-JSON: fica a mensagem genérica */ }
    throw new Error(detalhe);
  }
  return resposta.json();
}

function render(html) {
  if (estado.mapa) {
    estado.mapa.remove(); // limpar o mapa anterior antes de trocar de ecrã
    estado.mapa = null;
  }
  $app.innerHTML = `<section class="ecra">${html}</section>`;
  window.scrollTo({ top: 0, behavior: "auto" });

  // Acessibilidade: levar o foco (e os leitores de ecrã) ao título do
  // novo ecrã, em vez de o deixar perdido no fim da página.
  const foco = $app.querySelector("[data-foco]");
  if (foco) foco.focus({ preventScroll: true });
}

function horaLegivel(iso) {
  try {
    return new Date(iso).toLocaleTimeString(
      estado.lingua === "en" ? "en-GB" : "pt-PT",
      { hour: "2-digit", minute: "2-digit" }
    );
  } catch (_) {
    return "";
  }
}

function telHref(numero) {
  return "tel:" + String(numero).replace(/\s+/g, "");
}

function capitalizar(texto) {
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : "";
}

/* Aviso com prefixo "Importante:" invisível, lido pelos leitores de ecrã
   — truque do warning-callout do NHS design system. */
function aviso(html) {
  return `<div class="aviso"><span class="visualmente-oculto">${esc(t("aviso_importante"))}</span>${html}</div>`;
}

/* Esqueleto de carregamento: em vez de "A carregar…", mostra a silhueta
   do conteúdo que vem a caminho — a página parece mais rápida e não
   salta quando os dados chegam. */
function esqueleto(mensagem) {
  return `
    <div class="cartao" aria-busy="true" aria-label="${esc(t("a_carregar"))}">
      ${mensagem ? `<p class="texto-suave">${esc(mensagem)}</p>` : ""}
      <div class="esqueleto">
        <div class="esqueleto__linha esqueleto__linha--titulo"></div>
        <div class="esqueleto__linha"></div>
        <div class="esqueleto__linha esqueleto__linha--curta"></div>
        <div class="esqueleto__linha esqueleto__linha--botao"></div>
      </div>
    </div>
  `;
}

function mostrarErro(mensagem, tentarNovamente) {
  estado.renderAtual = () => mostrarErro(mensagem, tentarNovamente);
  render(`
    <div class="cartao">
      <h2 class="titulo-ecra" tabindex="-1" data-foco>${esc(t("erro_titulo"))}</h2>
      <p>${esc(mensagem)}</p>
      <p class="texto-suave">${esc(t("erro_ajuda"))}</p>
      <div class="botoes">
        <button class="botao" id="btn-tentar">${esc(t("tentar_novamente"))}</button>
        <button class="botao--fantasma" id="btn-recomecar">${esc(t("recomecar_inicio"))}</button>
      </div>
    </div>
  `);
  document.getElementById("btn-tentar").addEventListener("click", tentarNovamente);
  document.getElementById("btn-recomecar").addEventListener("click", recomecar);
}

function recomecar() {
  estado.queixa = null;
  estado.respostas = {};
  estado.historico = [];
  estado.resultado = null;
  ecraInicio();
}

/* ------------------------------------------------------- ecrã: início -- */

function ecraInicio() {
  estado.renderAtual = ecraInicio;
  render(`
    <div class="cartao">
      <h2 class="titulo-ecra" tabindex="-1" data-foco>${esc(t("inicio_titulo"))}</h2>
      <p>${esc(t("inicio_lead"))}</p>
      <ol class="passos">
        <li><div><strong>${esc(t("passo1_t"))}</strong>
          <span class="passos__desc">${esc(t("passo1_d"))}</span></div></li>
        <li><div><strong>${esc(t("passo2_t"))}</strong>
          <span class="passos__desc">${esc(t("passo2_d"))}</span></div></li>
        <li><div><strong>${esc(t("passo3_t"))}</strong>
          <span class="passos__desc">${esc(t("passo3_d"))}</span></div></li>
      </ol>
      <div class="botoes">
        <button class="botao" id="btn-comecar">${esc(t("comecar"))}</button>
      </div>
      <p class="selo-privacidade">${esc(t("selo_privacidade"))}</p>
    </div>
  `);
  document.getElementById("btn-comecar").addEventListener("click", ecraRedFlags);
}

/* ------------------------------------- ecrã: sinais de emergência ------ */

async function ecraRedFlags() {
  estado.renderAtual = ecraRedFlags;
  render(esqueleto());
  let sinais;
  try {
    sinais = await api("/api/red-flags");
  } catch (erro) {
    return mostrarErro(erro.message, ecraRedFlags);
  }

  const botoesSinais = sinais
    .map(
      (s) => `
      <button class="sinal-botao" data-id="${esc(s.id)}">${esc(campo(s, "texto"))}</button>`
    )
    .join("");

  render(`
    <div class="cartao">
      <h2 class="titulo-ecra" tabindex="-1" data-foco>${esc(t("rf_titulo"))}</h2>
      <p class="texto-suave">${esc(t("rf_sub"))}</p>
      <div class="botoes">
        <button class="botao" id="btn-nenhuma">${esc(t("rf_nenhuma"))}</button>
      </div>
      <p class="separador-sinais">${esc(t("rf_toque"))}</p>
      <div class="lista-sinais">${botoesSinais}</div>
      <div class="botoes">
        <button class="botao--fantasma" id="btn-recomecar">${esc(t("recomecar"))}</button>
      </div>
    </div>
  `);

  document.getElementById("btn-nenhuma").addEventListener("click", ecraQueixas);
  document.getElementById("btn-recomecar").addEventListener("click", recomecar);
  $app.querySelectorAll(".sinal-botao").forEach((botao) =>
    botao.addEventListener("click", async () => {
      try {
        const saida = await api("/api/triagem", { red_flags: [botao.dataset.id] });
        mostrarResultado(saida.resultado);
      } catch (erro) {
        mostrarErro(erro.message, ecraRedFlags);
      }
    })
  );
}

/* ------------------------------------------------ ecrã: escolher queixa -- */

function htmlQueixa(q, sugerida) {
  const etiqueta = sugerida
    ? ` <span class="etiqueta-sugestao">${esc(t("qx_sugestao"))}</span>`
    : "";
  return `
    <button class="queixa${sugerida ? " queixa--sugerida" : ""}" data-id="${esc(q.id)}">
      <span class="queixa__nome">${esc(campo(q, "nome"))}${etiqueta}</span>
      <span class="queixa__descricao">${esc(campo(q, "descricao"))}</span>
    </button>`;
}

function iniciarQueixa(id) {
  estado.queixa = id;
  estado.respostas = {};
  estado.historico = [];
  avancarTriagem();
}

async function ecraQueixas() {
  estado.renderAtual = ecraQueixas;
  render(esqueleto());
  let queixas;
  try {
    queixas = await api("/api/queixas");
  } catch (erro) {
    return mostrarErro(erro.message, ecraQueixas);
  }

  render(`
    <div class="cartao">
      <h2 class="titulo-ecra" tabindex="-1" data-foco>${esc(t("qx_titulo"))}</h2>
      <p class="texto-suave">${esc(t("qx_sub"))}</p>
      <div class="pesquisa">
        <label class="etiqueta" for="inp-pesquisa">${esc(t("qx_pesquisa_label"))}</label>
        <input class="campo campo--pesquisa" id="inp-pesquisa" type="search"
               placeholder="${esc(t("qx_pesquisa_placeholder"))}" autocomplete="off" />
        <div id="sugestoes" class="sugestoes" role="status" aria-live="polite"></div>
      </div>
      <div class="grelha-queixas">${queixas.map((q) => htmlQueixa(q, false)).join("")}</div>
      <div class="botoes">
        <button class="botao--fantasma" id="btn-recomecar">${esc(t("recomecar"))}</button>
      </div>
    </div>
  `);

  document.getElementById("btn-recomecar").addEventListener("click", recomecar);

  // Delegação num nó novo a cada render: cobre a grelha E as sugestões
  // injetadas depois, sem acumular listeners no #app.
  $app.querySelector(".cartao").addEventListener("click", (evento) => {
    const botao = evento.target.closest(".queixa");
    if (botao) iniciarQueixa(botao.dataset.id);
  });

  // Pesquisa em texto livre: sinónimos transparentes no backend
  // (GET /api/queixas/sugerir), sem inteligência artificial.
  const $entrada = document.getElementById("inp-pesquisa");
  const $sugestoes = document.getElementById("sugestoes");
  let temporizador = null;
  let pedidoAtual = 0;

  $entrada.addEventListener("input", () => {
    clearTimeout(temporizador);
    const texto = $entrada.value.trim();
    if (texto.length < 2) {
      $sugestoes.innerHTML = "";
      return;
    }
    temporizador = setTimeout(async () => {
      const pedido = ++pedidoAtual;
      try {
        const dados = await api(`/api/queixas/sugerir?q=${encodeURIComponent(texto)}`);
        if (pedido !== pedidoAtual) return; // resposta atrasada: ignorar
        $sugestoes.innerHTML = dados.sugestoes.length
          ? dados.sugestoes.map((q) => htmlQueixa(q, true)).join("")
          : `<p class="sugestoes__nota">${esc(t("qx_sem_sugestoes"))}</p>`;
      } catch (_) {
        $sugestoes.innerHTML = ""; // pesquisa é assistiva: falhar em silêncio
      }
    }, 250);
  });
}

/* --------------------------------------------- ecrã: perguntas em fases -- */

async function avancarTriagem() {
  try {
    const saida = await api("/api/triagem", {
      queixa: estado.queixa,
      respostas: estado.respostas,
    });
    if (saida.tipo === "pergunta") return ecraPergunta(saida);
    mostrarResultado(saida.resultado);
  } catch (erro) {
    mostrarErro(erro.message, avancarTriagem);
  }
}

function voltarAtras() {
  const ultima = estado.historico.pop();
  if (ultima) delete estado.respostas[ultima.id];
  avancarTriagem();
}

function ecraPergunta(saida) {
  estado.renderAtual = () => ecraPergunta(saida);
  const { pergunta, progresso } = saida;
  const numero = progresso.respondidas + 1;
  const fase = pergunta.fase || 2;
  const podeVoltar = estado.historico.length > 0;

  const passos = [1, 2, 3]
    .map(
      (n) =>
        `<span class="fases__passo ${n <= fase ? "fases__passo--ativo" : ""}"></span>`
    )
    .join("");

  const ajuda = campo(pergunta, "ajuda");

  render(`
    <div class="cartao">
      <div class="progresso">
        <div class="fases" aria-hidden="true">${passos}</div>
        <p class="progresso__fase">${esc(t("fase_de", fase, t("fases")[fase]))}</p>
        <p class="progresso__texto">${esc(t("pergunta_n", numero))}</p>
      </div>
      <p class="pergunta__texto" tabindex="-1" data-foco>${esc(campo(pergunta, "texto"))}</p>
      ${ajuda ? `<p class="pergunta__ajuda">${esc(ajuda)}</p>` : ""}
      <div class="botoes-sim-nao">
        <button class="botao" data-valor="sim">${esc(t("sim"))}</button>
        <button class="botao botao--secundario" data-valor="nao">${esc(t("nao"))}</button>
      </div>
      <div class="botoes">
        ${podeVoltar ? `<button class="botao--fantasma" id="btn-voltar">${esc(t("voltar_pergunta"))}</button>` : ""}
        <button class="botao--fantasma" id="btn-recomecar">${esc(t("recomecar"))}</button>
      </div>
    </div>
  `);

  document.getElementById("btn-recomecar").addEventListener("click", recomecar);
  if (podeVoltar) {
    document.getElementById("btn-voltar").addEventListener("click", voltarAtras);
  }
  $app.querySelectorAll("[data-valor]").forEach((botao) =>
    botao.addEventListener("click", () => {
      const valor = botao.dataset.valor;
      estado.historico.push({
        id: pergunta.id,
        texto: campo(pergunta, "texto"),
        resposta: valor,
      });
      estado.respostas[pergunta.id] = valor;
      avancarTriagem();
    })
  );
}

/* ---------------------------------------------------- ecrã: resultado -- */

function mostrarResultado(resultado) {
  estado.renderAtual = () => mostrarResultado(resultado);
  estado.resultado = resultado;
  const info = resultado.cor_info;
  const eVermelho = resultado.cor === "vermelho";
  const motivo = campo(resultado, "motivo");
  const nota = campo(resultado, "nota");

  const resumoRespostas = estado.historico.length
    ? `
      <details class="respostas">
        <summary>${esc(t("res_resumo"))}</summary>
        <ul>
          ${estado.historico
            .map(
              (h) =>
                `<li>${esc(h.texto)}: <strong>${esc(h.resposta === "sim" ? t("sim") : t("nao"))}</strong></li>`
            )
            .join("")}
        </ul>
        <p class="texto-suave">${esc(t("res_resumo_dica"))}</p>
      </details>`
    : "";

  render(`
    <div class="cartao">
      <p class="pulseira-rotulo" tabindex="-1" data-foco>${esc(t("res_rotulo"))}</p>
      <div class="pulseira pulseira--${esc(resultado.cor)}">
        <span class="pulseira__nome">${esc(campo(info, "nome"))}</span>
        <span class="pulseira__classificacao">${esc(campo(info, "classificacao"))}</span>
      </div>
      <p class="resultado__tempo">${esc(campo(info, "tempo_alvo"))}</p>
      <p class="resultado__motivo">${esc(campo(info, "descricao"))}</p>
      ${motivo ? `<p class="resultado__motivo">${esc(motivo)}</p>` : ""}
      ${nota ? `<p class="resultado__nota">${esc(nota)}</p>` : ""}
      ${resumoRespostas}
      ${aviso(t("res_aviso"))}
      <div class="botoes">
        ${
          eVermelho
            ? `<a class="botao botao--112" href="tel:112">${esc(t("res_112"))}</a>
               <button class="botao botao--secundario" id="btn-onde">${esc(t("res_ver_urgencia"))}</button>`
            : `<button class="botao" id="btn-onde">${esc(t("res_onde"))}</button>`
        }
        <button class="botao--fantasma" id="btn-recomecar">${esc(t("recomecar"))}</button>
      </div>
    </div>
  `);

  document.getElementById("btn-recomecar").addEventListener("click", recomecar);
  document.getElementById("btn-onde").addEventListener("click", pedirLocalizacao);
}

/* -------------------------------------------------------- localização -- */

function pedirLocalizacao() {
  if (!navigator.geolocation) {
    return ecraLocalManual("loc_sem_suporte");
  }

  render(`<div class="cartao"><p>${esc(t("loc_obter"))}</p>
    <p class="texto-suave">${esc(t("loc_permitir"))}</p></div>`);

  navigator.geolocation.getCurrentPosition(
    (posicao) => {
      const { latitude, longitude, accuracy } = posicao.coords;
      usarLocalizacao({
        lat: latitude,
        lng: longitude,
        precisao: Number.isFinite(accuracy) ? Math.round(accuracy) : null,
        origem: "auto",
        rotulo: null,
      });
    },
    () => ecraLocalManual("loc_falhou"),
    // enableHighAccuracy: em telemóveis liga o GPS a sério; em
    // computadores não muda muito (a posição vem da rede), por isso
    // mostramos a precisão ao utente e deixamo-lo corrigir.
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
  );
}

function usarLocalizacao(localizacao) {
  estado.localizacao = localizacao;
  obterEncaminhamento();
}

function precisaoLegivel(metros) {
  if (!metros) return "";
  if (metros < 1000) return `${metros} m`;
  const km = metros / 1000;
  return `${km >= 10 ? Math.round(km) : km.toFixed(1)} km`;
}

async function ecraLocalManual(motivoChave) {
  estado.renderAtual = () => ecraLocalManual(motivoChave);
  try {
    if (!estado.unidades) estado.unidades = await api("/api/unidades");
  } catch (erro) {
    return mostrarErro(erro.message, () => ecraLocalManual(motivoChave));
  }

  // Coordenadas aproximadas por concelho = coordenadas da 1.ª unidade dele.
  const porConcelho = new Map();
  for (const u of estado.unidades) {
    if (!porConcelho.has(u.concelho)) porConcelho.set(u.concelho, u);
  }
  const opcoes = [...porConcelho.keys()]
    .sort((a, b) => a.localeCompare(b, "pt"))
    .map((c) => `<option value="${esc(c)}">${esc(c)}</option>`)
    .join("");

  render(`
    <div class="cartao">
      <h2 class="titulo-ecra" tabindex="-1" data-foco>${esc(t("loc_titulo"))}</h2>
      <p class="texto-suave">${esc(t(motivoChave))}</p>
      <select class="campo" id="sel-concelho" aria-label="${esc(t("loc_aria_concelho"))}">${opcoes}</select>
      <div class="botoes">
        <button class="botao" id="btn-usar">${esc(t("loc_usar"))}</button>
        <button class="botao botao--secundario" id="btn-gps">${esc(t("loc_gps"))}</button>
        <button class="botao--fantasma" id="btn-recomecar">${esc(t("recomecar"))}</button>
      </div>
    </div>
  `);

  document.getElementById("btn-recomecar").addEventListener("click", recomecar);
  document.getElementById("btn-gps").addEventListener("click", pedirLocalizacao);
  document.getElementById("btn-usar").addEventListener("click", () => {
    const escolhido = document.getElementById("sel-concelho").value;
    const unidade = porConcelho.get(escolhido);
    usarLocalizacao({
      lat: unidade.lat,
      lng: unidade.lng,
      precisao: null,
      origem: "concelho",
      rotulo: escolhido,
    });
  });
}

/* ------------------------------------------------ ecrã: encaminhamento -- */

async function obterEncaminhamento() {
  const loc = estado.localizacao;
  render(esqueleto(t("loc_obter")));
  // Aquece o cache de tempos de espera antes de decidir. Se falhar
  // (sem internet, site em baixo), o encaminhamento segue à mesma.
  try {
    await api("/api/espera");
  } catch (_) {
    /* sem tempos: o encaminhamento decide por distância e horários */
  }
  try {
    const corpo = { cor: estado.resultado.cor, lat: loc.lat, lng: loc.lng };
    if (estado.horaSimulada) corpo.quando = estado.horaSimulada;
    const dados = await api("/api/encaminhamento", corpo);
    ecraEncaminhamento(dados, loc);
  } catch (erro) {
    mostrarErro(erro.message, obterEncaminhamento);
  }
}

function htmlUnidade(u, comMapa) {
  const rotuloServico = t("un_servico");
  const rotuloTipo = t("un_tipo");
  const horarios = Object.entries(u.horarios || {})
    .map(([s, texto]) => `<li><strong>${esc(rotuloServico[s] || s)}:</strong> ${esc(texto)}</li>`)
    .join("");
  const reabre = campo(u, "proxima_abertura_texto");

  return `
    <div class="cartao unidade">
      <div class="unidade__cabecalho">
        <div>
          <h3 class="unidade__nome">${esc(u.nome)}</h3>
          <p class="unidade__meta">${esc(rotuloTipo[u.tipo] || u.tipo)},
            ${esc(u.concelho)}, ${esc(t("un_km", u.distancia_km))}</p>
        </div>
        <span class="chip ${u.aberta_agora ? "chip--aberto" : "chip--fechado"}">
          ${esc(u.aberta_agora ? t("un_aberta") : t("un_fechada"))}
        </span>
      </div>
      ${
        u.aberta_agora && u.tempo_espera
          ? `<p class="unidade__espera">${esc(t("esp_linha", u.tempo_espera))}</p>`
          : ""
      }
      ${
        !u.aberta_agora && reabre
          ? `<p class="unidade__reabre">${esc(capitalizar(reabre))}.</p>`
          : ""
      }
      ${horarios ? `<ul class="unidade__horarios">${horarios}</ul>` : ""}
      ${u.morada ? `<p class="unidade__meta">${esc(u.morada)}</p>` : ""}
      ${u.notas ? `<p class="unidade__meta">${esc(u.notas)}</p>` : ""}
      ${u.dados_confirmados ? "" : aviso(esc(t("un_reconfirmar")))}
      <div class="botoes">
        ${
          u.telefone
            ? `<a class="botao botao--secundario" href="${telHref(u.telefone)}">${esc(t("un_ligar", u.telefone))}</a>`
            : ""
        }
        <a class="botao botao--secundario" target="_blank" rel="noopener"
           href="https://www.google.com/maps/dir/?api=1&destination=${u.lat},${u.lng}">
          ${esc(t("un_gmaps"))}
        </a>
      </div>
      ${
        comMapa
          ? `
      <div class="qr-nav" id="qr-nav" hidden>
        <span class="qr-nav__codigo" id="qr-codigo" aria-hidden="true"></span>
        <div>
          <strong>${esc(t("qr_titulo"))}</strong>
          <p class="texto-suave">${esc(t("qr_dica"))}</p>
        </div>
      </div>
      <div class="mapa" id="mapa"></div>`
          : ""
      }
    </div>
  `;
}

function htmlAutocuidado(ac) {
  const lista = (itens, classe) =>
    itens.length
      ? `<ul class="${classe}">${itens.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`
      : "";

  // Cartões de cuidado (estrutura do NHS design system, cores nossas):
  // faixa de cabeçalho + corpo. Azul institucional para "cuidar-se em
  // casa"; vermelho da paleta de triagem para "procure ajuda se".
  return `
    <div class="cartao cartao-cuidado">
      <div class="cartao-cuidado__cabecalho cartao-cuidado__cabecalho--info">
        <h3>${esc(campo(ac, "titulo"))}</h3>
      </div>
      <div class="cartao-cuidado__corpo">
        <p>${esc(campo(ac, "intro") || ac.texto || "")}</p>
        ${lista(campoLista(ac, "fazer"), "lista-fazer")}
        ${lista(campoLista(ac, "evitar"), "lista-evitar")}
        <div class="botoes no-print">
          <a class="botao botao--secundario" href="tel:808242424">${esc(t("ac_ligar_sns"))}</a>
        </div>
      </div>
    </div>
    <div class="cartao cartao-cuidado">
      <div class="cartao-cuidado__cabecalho cartao-cuidado__cabecalho--alerta">
        <h3>${esc(campo(ac, "alerta_titulo") || t("ac_alerta_titulo"))}</h3>
      </div>
      <div class="cartao-cuidado__corpo">
        ${lista(campoLista(ac, "alerta"), "lista-alerta")}
      </div>
    </div>`;
}

function ecraEncaminhamento(dados, utente) {
  estado.renderAtual = () => ecraEncaminhamento(dados, utente);

  const alternativas = (dados.alternativas || [])
    .map((a) => {
      const reabre = campo(a, "proxima_abertura_texto");
      const espMin =
        a.aberta_agora && a.tempo_espera && a.tempo_espera.minutos != null
          ? `, ~${a.tempo_espera.minutos} min ${t("esp_curto")}`
          : "";
      return `
      <div class="alternativa">
        <div>
          <div class="alternativa__nome">${esc(a.nome)}</div>
          <div class="alternativa__meta">${esc(a.concelho)}, ${esc(a.distancia_km)} km,
            ${a.aberta_agora
              ? esc(t("alt_aberto"))
              : `${esc(t("alt_fechado"))}${reabre ? `, ${esc(reabre)}` : ""}`}${esc(espMin)}</div>
        </div>
        <a class="ligacao" target="_blank" rel="noopener"
           href="https://www.google.com/maps/dir/?api=1&destination=${a.lat},${a.lng}">${esc(t("direcoes"))}</a>
      </div>`;
    })
    .join("");

  const centroLocal = dados.centro_saude_proximo
    ? `
      <div class="cartao">
        <h3 class="unidade__nome">${esc(t("persistir_titulo"))}</h3>
        <p class="texto-suave">${esc(t("persistir_texto"))}</p>
      </div>
      ${htmlUnidade(dados.centro_saude_proximo, false)}`
    : "";

  const hora = horaLegivel(dados.gerado_em);
  const diaDescricao = dados.dia && dados.dia.descricao ? dados.dia.descricao : "";

  // Como foi obtida a localização — e a hipótese de a corrigir. Nos
  // computadores a posição vem da rede e cai muitas vezes no centro do
  // Funchal; ser transparente evita recomendações "misteriosas".
  const precisao = utente.origem === "auto" ? utente.precisao : null;
  const localTexto =
    utente.origem === "concelho"
      ? t("loc_usada_concelho", esc(utente.rotulo))
      : t("loc_usada_auto", precisao ? esc(precisaoLegivel(precisao)) : "");
  const avisoPrecisao =
    utente.origem === "auto" && precisao && precisao > 3000
      ? `<p class="local-aviso">${esc(t("aviso_precisao"))}</p>`
      : "";

  // A mensagem longa do encaminhamento é gerada pelo backend em
  // português; no modo EN marcamos o parágrafo com lang="pt" para os
  // leitores de ecrã a pronunciarem bem.
  const langMensagem = estado.lingua === "en" ? ' lang="pt"' : "";

  // Linha de estado dos tempos de espera: "atualizados às HH:MM" quando
  // os temos, aviso de indisponível nas cores em que isso importa.
  const espInfo = dados.espera_info || {};
  let infoEspera = "";
  if (espInfo.disponivel) {
    const horaEsp = espInfo.obtido_em ? horaLegivel(espInfo.obtido_em) : "";
    infoEspera = `<p class="texto-suave espera-estado">${esc(t("esp_atualizado", horaEsp))}${
      espInfo.desatualizado ? " " + esc(t("esp_desatualizado")) : ""
    }</p>`;
  } else if (dados.cor === "laranja" || dados.cor === "amarelo") {
    infoEspera = `<p class="texto-suave espera-estado">${esc(t("esp_indisponivel"))}</p>`;
  }

  render(`
    ${
      estado.horaSimulada
        ? `<div class="faixa-demo">${esc(t("faixa_demo", estado.horaSimulada))}</div>`
        : ""
    }
    <div class="cartao">
      <h2 class="titulo-ecra" tabindex="-1" data-foco>${esc(t("enc_titulos")[dados.acao] || t("enc_recomendacao"))}</h2>
      <p${langMensagem}>${esc(dados.mensagem)}</p>
      ${hora ? `<p class="texto-suave">${esc(t("enc_calculo", hora, diaDescricao))}</p>` : ""}
      ${infoEspera}
      <div class="local-linha no-print">
        <span class="texto-suave">${esc(t("loc_usada_prefixo"))}${localTexto}.</span>
        <button class="ligacao ligacao--botao" id="btn-alterar-local">${esc(t("alterar_local"))}</button>
      </div>
      ${avisoPrecisao}
      ${
        dados.acao === "ligar_112"
          ? `<div class="botoes"><a class="botao botao--112" href="tel:112">${esc(t("res_112"))}</a></div>`
          : ""
      }
    </div>
    ${dados.autocuidado ? htmlAutocuidado(dados.autocuidado) : ""}
    ${dados.unidade ? htmlUnidade(dados.unidade, true) : ""}
    ${
      alternativas
        ? `<div class="cartao alternativas"><h3 class="unidade__nome">${esc(t("alt_titulo"))}</h3>${alternativas}</div>`
        : ""
    }
    ${centroLocal}
    <div class="cartao">
      <h3 class="unidade__nome">${esc(t("contactos_titulo"))}</h3>
      <div class="contactos">
        <a class="contacto" href="tel:112">
          <span class="contacto__nome">${esc(t("ct_emergencia"))}</span><br />
          <span class="contacto__numero">112</span>
        </a>
        <a class="contacto" href="tel:808242424">
          <span class="contacto__nome">${esc(t("ct_sns"))}</span><br />
          <span class="contacto__numero">808 24 24 24</span>
        </a>
      </div>
      <div class="botoes no-print">
        <button class="botao botao--secundario" id="btn-imprimir">${esc(t("imprimir"))}</button>
        <button class="botao--fantasma" id="btn-recomecar">${esc(t("nova_avaliacao"))}</button>
      </div>
    </div>
  `);

  document.getElementById("btn-recomecar").addEventListener("click", recomecar);
  document.getElementById("btn-imprimir").addEventListener("click", () => window.print());
  document
    .getElementById("btn-alterar-local")
    .addEventListener("click", () => ecraLocalManual("loc_alterar"));
  if (dados.unidade) {
    iniciarMapa(dados, utente);
    preencherQR(dados.unidade);
  }
}

/* QR com as direções do Google Maps para a unidade recomendada: lê-se
   com a câmara do telemóvel (útil quando a avaliação é feita num
   computador) e sai também na impressão. Gerado localmente, sem chamadas
   de rede (biblioteca qrcode-generator, MIT); se a biblioteca não
   carregar, o bloco simplesmente não aparece. */
function preencherQR(unidade) {
  const bloco = document.getElementById("qr-nav");
  const alvo = document.getElementById("qr-codigo");
  if (!bloco || !alvo || typeof qrcode === "undefined") return;
  try {
    const url = `https://www.google.com/maps/dir/?api=1&destination=${unidade.lat},${unidade.lng}`;
    const qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    alvo.innerHTML = qr.createSvgTag(3, 2);
    bloco.hidden = false;
  } catch (_) {
    /* sem QR: o resto do ecrã continua a funcionar */
  }
}

function iniciarMapa(dados, utente) {
  const div = document.getElementById("mapa");
  if (!div) return;
  if (typeof L === "undefined") {
    div.outerHTML = `<p class="texto-suave">${esc(t("mapa_indisponivel"))}</p>`;
    return;
  }

  const mapa = L.map("mapa");
  estado.mapa = mapa;

  // Tiles claros e discretos (CARTO sobre dados OpenStreetMap): o mapa
  // deixa de "gritar" no meio da página e os marcadores ganham destaque.
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    maxZoom: 19,
    subdomains: "abcd",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(mapa);

  const pontos = [];

  // A unidade recomendada leva um marcador na COR DA TRIAGEM — a mesma
  // linguagem visual da guia de encaminhamento, agora no mapa.
  const corTriagem =
    (estado.resultado && estado.resultado.cor_info && estado.resultado.cor_info.hex) ||
    "#185fa5";

  const u = dados.unidade;
  L.circleMarker([u.lat, u.lng], {
    radius: 11,
    color: "#ffffff",
    weight: 3,
    fillColor: corTriagem,
    fillOpacity: 1,
  })
    .addTo(mapa)
    .bindPopup(u.nome)
    .openPopup();
  pontos.push([u.lat, u.lng]);

  for (const alt of dados.alternativas || []) {
    L.circleMarker([alt.lat, alt.lng], {
      radius: 7,
      color: "#ffffff",
      weight: 2,
      fillColor: "#7c8894",
      fillOpacity: 0.9,
    })
      .addTo(mapa)
      .bindPopup(alt.nome);
    pontos.push([alt.lat, alt.lng]);
  }

  L.circleMarker([utente.lat, utente.lng], {
    radius: 9,
    color: "#185fa5",
    fillColor: "#185fa5",
    fillOpacity: 0.85,
  })
    .addTo(mapa)
    .bindPopup(
      utente.origem === "concelho" ? t("mapa_aprox", utente.rotulo) : t("mapa_voce")
    );
  pontos.push([utente.lat, utente.lng]);

  // Círculo de precisão: torna visível a incerteza da localização
  // automática (num PC pode ser de vários quilómetros). Não entra no
  // enquadramento para não afastar demasiado o zoom.
  if (utente.origem === "auto" && utente.precisao) {
    L.circle([utente.lat, utente.lng], {
      radius: utente.precisao,
      color: "#185fa5",
      weight: 1,
      fillColor: "#185fa5",
      fillOpacity: 0.08,
    }).addTo(mapa);
  }

  mapa.fitBounds(L.latLngBounds(pontos), { padding: [40, 40] });
}

/* ---------------------------------------------------------------- boot -- */

estado.lingua = linguaInicial();
aplicarLinguaEstatica();

const $btnLingua = document.getElementById("btn-lingua");
if ($btnLingua) {
  $btnLingua.addEventListener("click", () => {
    estado.lingua = estado.lingua === "pt" ? "en" : "pt";
    try {
      localStorage.setItem("ondeir.lingua", estado.lingua);
    } catch (_) { /* localStorage bloqueado: a escolha vale só nesta página */ }
    aplicarLinguaEstatica();
    if (estado.renderAtual) estado.renderAtual();
    else ecraInicio();
  });
}

ecraInicio();
