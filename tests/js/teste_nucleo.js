/* Testes do núcleo do frontend (Node, sem browser) — v0.15.2.

   O que está aqui fixado é a PROPRIEDADE DE SEGURANÇA do aconselhamento:
   o utente só vê itens com texto_utente, e NUNCA o texto clínico — em
   nenhuma língua, com nenhuma entrada malformada. Antes da v0.15.2 esta
   garantia vivia dentro de app.js sem qualquer teste; se alguém
   "melhorasse" o filtro para recuar para o texto clínico, nada apanhava.

   Correr localmente:  node --test tests/js/teste_nucleo.js
   No CI corre a seguir ao pytest (ver .github/workflows/ci.yml); há também
   um embrulho em tests/test_v15_2.py que o corre via subprocess, para
   `python -m pytest` continuar a ser o único comando necessário. */

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const Nucleo = require(path.join(__dirname, "..", "..", "static", "js", "nucleo.js"));

const CLINICO = "Avaliar escala de Cincinnati e ativar via verde do AVC";

test("item sem texto_utente fica invisível — nunca se mostra o texto clínico", () => {
  const itens = [{ texto: CLINICO }];
  assert.deepEqual(Nucleo.conselhosParaMostrar(itens, "pt"), []);
  assert.deepEqual(Nucleo.conselhosParaMostrar(itens, "en"), []);
});

test("o texto clínico nunca aparece, mesmo quando há versão de utente", () => {
  const itens = [
    { texto: CLINICO, texto_utente: "Ligue 112.", texto_utente_en: "Call 112." },
    { texto: "Administrar glucagon IM" },
  ];
  for (const lingua of ["pt", "en", "??", undefined]) {
    const saida = Nucleo.conselhosParaMostrar(itens, lingua);
    assert.ok(!saida.join(" ").includes("Cincinnati"));
    assert.ok(!saida.join(" ").includes("glucagon"));
  }
});

test("porta é o texto_utente PT: um _en órfão não abre o item", () => {
  // Por construção o aplicar nunca gera isto, mas o filtro tem de ser
  // defensivo: sem PT, o item está oculto MESMO em inglês.
  const itens = [{ texto: CLINICO, texto_utente_en: "Call 112." }];
  assert.deepEqual(Nucleo.conselhosParaMostrar(itens, "en"), []);
});

test("em inglês usa-se o _en; sem tradução recua-se para o PT (nunca para o clínico)", () => {
  const itens = [
    { texto: "A", texto_utente: "Beba água.", texto_utente_en: "Drink water." },
    { texto: "B", texto_utente: "Descanse." },
  ];
  assert.deepEqual(Nucleo.conselhosParaMostrar(itens, "en"),
    ["Drink water.", "Descanse."]);
  assert.deepEqual(Nucleo.conselhosParaMostrar(itens, "pt"),
    ["Beba água.", "Descanse."]);
});

test("ordem da tabela preservada (o 1.º é a ação principal)", () => {
  const itens = [
    { texto: "1", texto_utente: "Primeiro gesto." },
    { texto: "2", texto_utente: "Segundo gesto." },
    { texto: "3", texto_utente: "Terceiro gesto." },
  ];
  assert.deepEqual(Nucleo.conselhosParaMostrar(itens, "pt"),
    ["Primeiro gesto.", "Segundo gesto.", "Terceiro gesto."]);
});

test("desduplicação ao nível do texto mostrado, na língua ativa", () => {
  const itens = [
    { texto: "paracetamol", texto_utente: "Pode tomar um analgésico (dose da bula).",
      texto_utente_en: "You can take a painkiller (dose on the leaflet)." },
    { texto: "paracetamol ou ibuprofeno",
      texto_utente: "Pode tomar  um analgésico (dose da bula).", // espaços ≠
      texto_utente_en: "You can take pain relief if needed." },
  ];
  // Em PT as duas frases colapsam (espaços colapsados, minúsculas);
  // em EN são distintas e mostram-se as duas.
  assert.equal(Nucleo.conselhosParaMostrar(itens, "pt").length, 1);
  assert.equal(Nucleo.conselhosParaMostrar(itens, "en").length, 2);
});

test("entradas malformadas dão lista vazia, sem lançar", () => {
  for (const errado of [null, undefined, {}, "texto", 42, [null, {}, { texto: "x" }, { texto_utente: "  " }]]) {
    const saida = Nucleo.conselhosParaMostrar(errado, "pt");
    assert.deepEqual(saida, []);
  }
});

test("textoUtenteDoItem: contrato item a item", () => {
  assert.equal(Nucleo.textoUtenteDoItem(null, "pt"), "");
  assert.equal(Nucleo.textoUtenteDoItem({ texto: CLINICO }, "pt"), "");
  assert.equal(
    Nucleo.textoUtenteDoItem({ texto_utente: " Ligue 112. " }, "pt"),
    "Ligue 112.");
  assert.equal(
    Nucleo.textoUtenteDoItem(
      { texto_utente: "Ligue 112.", texto_utente_en: "Call 112." }, "en"),
    "Call 112.");
});

/* ------------------------------------------------- textoNaLingua (v0.15.3) */

test("textoNaLingua: em inglês usa o _en quando existe; senão o PT", () => {
  const perg = { texto: "Tem dor torácica?", texto_en: "Do you have chest pain?" };
  assert.equal(Nucleo.textoNaLingua(perg, "texto", "en"), "Do you have chest pain?");
  assert.equal(Nucleo.textoNaLingua(perg, "texto", "pt"), "Tem dor torácica?");
});

test("textoNaLingua: _en vazio ou ausente recua para o PT (omissão segura)", () => {
  assert.equal(
    Nucleo.textoNaLingua({ texto: "Sente falta de ar?", texto_en: "" }, "texto", "en"),
    "Sente falta de ar?");
  assert.equal(
    Nucleo.textoNaLingua({ texto: "Sente falta de ar?" }, "texto", "en"),
    "Sente falta de ar?");
});

test("textoNaLingua: objeto-pergunta do motor com texto_utente já escolhido", () => {
  // O servidor (motor) recua texto_utente→texto ANTES de responder; ao
  // frontend chega um único par texto/texto_en, e a escolha bilingue é esta.
  const doMotor = { texto: "A dor aperta como um peso no peito?",
                    texto_en: "Does the pain squeeze like a weight on your chest?" };
  assert.equal(Nucleo.textoNaLingua(doMotor, "texto", "en"),
    "Does the pain squeeze like a weight on your chest?");
});

test("textoNaLingua: null/undefined/malformado dão \"\" — nunca `undefined` no ecrã", () => {
  assert.equal(Nucleo.textoNaLingua(null, "texto", "pt"), "");
  assert.equal(Nucleo.textoNaLingua(undefined, "texto", "en"), "");
  assert.equal(Nucleo.textoNaLingua("texto", "texto", "pt"), "");
  assert.equal(Nucleo.textoNaLingua({}, "texto", "pt"), "");
  assert.equal(Nucleo.textoNaLingua({ texto: null }, "texto", "pt"), "");
});

test("textoNaLingua: valores não-texto passam intactos (campoLista depende disto)", () => {
  const obj = { itens: ["a", "b"], itens_en: ["c"] };
  assert.deepEqual(Nucleo.textoNaLingua(obj, "itens", "pt"), ["a", "b"]);
  assert.deepEqual(Nucleo.textoNaLingua(obj, "itens", "en"), ["c"]);
});

test("textoNaLingua: língua desconhecida comporta-se como PT", () => {
  const perg = { texto: "Tem febre?", texto_en: "Do you have a fever?" };
  for (const lingua of ["fr", "", undefined, null]) {
    assert.equal(Nucleo.textoNaLingua(perg, "texto", lingua), "Tem febre?");
  }
});
