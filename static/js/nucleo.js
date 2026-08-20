/* ==========================================================================
   Onde ir? Núcleo testável do frontend (v0.15.2).

   Aqui vivem as funções PURAS de que depende a segurança do que o utente
   vê — sem DOM, sem estado global, sem rede. A razão de existir: a rede de
   segurança do aconselhamento ("o doente só vê itens com texto_utente")
   vivia dentro de app.js, sem nenhum teste; se alguém "melhorasse" o filtro
   para recuar para o texto clínico, nada apanhava isso. Agora a propriedade
   está isolada aqui e fixada por testes que correm em Node
   (tests/js/teste_nucleo.js, também no CI); o app.js limita-se a pintar o
   que estas funções devolvem.

   Carregamento duplo de propósito:
     - no browser: define window.Nucleo (o index.html carrega este ficheiro
       ANTES de app.js);
     - em Node: module.exports, para os testes fazerem require() direto.

   REGRA DE OURO (não mexer sem ler docs/GUIA_DOS_DADOS.md): o aconselhamento
   clínico da tabela está escrito para o PROFISSIONAL. Ao contrário das
   perguntas, aqui NÃO há recuo para o texto clínico (`texto`): item sem
   `texto_utente` é item invisível para o utente, em qualquer língua.
   ========================================================================== */

(function (raiz) {
  "use strict";

  /* Texto a mostrar ao utente para UM item de aconselhamento, na língua
     pedida — ou "" se o item não pode ser mostrado.

     - A PORTA é sempre o texto_utente PT: sem ele, o item está oculto,
       mesmo que (por absurdo) trouxesse um texto_utente_en.
     - Em inglês usa-se texto_utente_en; se faltar, recua-se para o PT
       (mostrar português a um visitante é seguro; mostrar o texto clínico
       não é, e por isso NUNCA se devolve `texto`). */
  function textoUtenteDoItem(item, lingua) {
    if (!item || typeof item !== "object") return "";
    var pt = typeof item.texto_utente === "string" ? item.texto_utente.trim() : "";
    if (!pt) return "";
    if (lingua === "en") {
      var en = typeof item.texto_utente_en === "string" ? item.texto_utente_en.trim() : "";
      if (en) return en;
    }
    return pt;
  }

  /* Lista final de conselhos a mostrar, pela ordem da tabela (o primeiro é a
     ação principal), já desduplicada ao nível do TEXTO MOSTRADO na língua
     ativa: dois conselhos clínicos distintos podem colapsar na mesma frase
     leiga (p. ex. "paracetamol" e "paracetamol ou ibuprofeno") e o utente
     não deve ver dois pontos quase iguais. Entradas malformadas (null, não
     lista, itens sem texto_utente) resultam em lista vazia/ausência — nunca
     em texto clínico. */
  function conselhosParaMostrar(itens, lingua) {
    if (!Array.isArray(itens)) return [];
    var vistos = Object.create(null);
    var saida = [];
    for (var i = 0; i < itens.length; i++) {
      var txt = textoUtenteDoItem(itens[i], lingua);
      if (!txt) continue;
      var chave = txt.replace(/\s+/g, " ").toLowerCase();
      if (vistos[chave]) continue;
      vistos[chave] = true;
      saida.push(txt);
    }
    return saida;
  }

  /* Escolha bilingue GENÉRICA para conteúdo clínico vindo da API (novo na
     v0.15.3): devolve obj[nome + "_en"] quando a língua é inglês e esse
     campo existe com valor; caso contrário obj[nome]; e "" para null/
     undefined/objeto malformado. É a regra que o campo() do app.js sempre
     aplicou — agora vive aqui, com testes em Node, porque é dela que
     depende "o utente nunca vê a língua errada nem `undefined` no ecrã".

     Nota: ao contrário de textoUtenteDoItem, esta função NÃO é uma porta
     de segurança — devolve o valor tal como está (pode ser lista, no caso
     de campos *_lista). A porta do aconselhamento continua a ser
     textoUtenteDoItem; a das perguntas é o servidor (portão do motor). */
  function textoNaLingua(obj, nome, lingua) {
    if (!obj || typeof obj !== "object") return "";
    if (lingua === "en" && obj[nome + "_en"]) return obj[nome + "_en"];
    var valor = obj[nome];
    return valor === undefined || valor === null ? "" : valor;
  }

  var Nucleo = {
    textoUtenteDoItem: textoUtenteDoItem,
    conselhosParaMostrar: conselhosParaMostrar,
    textoNaLingua: textoNaLingua,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = Nucleo; // Node (testes)
  } else {
    raiz.Nucleo = Nucleo; // browser
  }
})(typeof window !== "undefined" ? window : globalThis);
