/* ==========================================================================
   Onde ir? Textos da interface em português e inglês. Versão 0.6.

   Padrão inspirado no projeto aberto do governo do Ontário
   (covid-19-self-assessment): cada chave existe nas duas línguas.
   Para mudar um texto do interface, edita-se AQUI — sem tocar na lógica.

   Notas:
   - Valores podem ser strings, objetos (mapas de rótulos) ou funções
     (textos com partes variáveis).
   - Os conteúdos CLÍNICOS (perguntas, sinais, autocuidado) não vivem
     aqui: vêm da API com campos *_en opcionais nos ficheiros de dados
     (ver app/data/rules/febre.json como modelo). Quando falta o inglês,
     a aplicação mostra o português.
   ========================================================================== */

"use strict";

const TEXTOS = {
  pt: {
    topo_sub: "Orientação de utentes na Região Autónoma da Madeira · protótipo",
    rodape_aviso:
      '<strong>Aviso:</strong> esta ferramenta dá orientação geral e ' +
      '<strong>não substitui</strong> a avaliação de um profissional de saúde ' +
      'nem a triagem feita na urgência. Em situação de emergência, ligue ' +
      '<a href="tel:112">112</a>. Aconselhamento: SNS&nbsp;24, ' +
      '<a href="tel:808242424">808&nbsp;24&nbsp;24&nbsp;24</a>.',
    rodape_nota:
      "Protótipo académico, versão 0.8. Regras e dados de unidades por validar com o SESARAM.",
    lingua_aria: "Switch to English",

    a_carregar: "A carregar",
    erro_titulo: "Algo correu mal",
    erro_ajuda:
      "Se o problema persistir e precisar de ajuda, ligue para o SNS 24 (808 24 24 24) ou, em emergência, para o 112.",
    tentar_novamente: "Tentar novamente",
    recomecar_inicio: "Recomeçar do início",
    recomecar: "Recomeçar",
    aviso_importante: "Importante: ",

    inicio_titulo: "Não sabe se deve ir à urgência?",
    inicio_lead:
      "Responda a perguntas simples sobre o que sente e indicamos-lhe a prioridade estimada e a unidade de saúde certa, perto de si. Demora cerca de um minuto.",
    passo1_t: "Sinais de emergência",
    passo1_d: "Confirmamos primeiro que não é um caso para o 112.",
    passo2_t: "Perguntas sobre o que sente",
    passo2_d: "Respostas de sim ou não, em linguagem simples.",
    passo3_t: "Recomendação",
    passo3_d: "A prioridade estimada e a unidade adequada que está aberta.",
    comecar: "Começar",
    selo_privacidade:
      "Não guardamos nenhum dado seu. As respostas desaparecem quando fecha a página.",

    rf_titulo: "Primeiro, situações de emergência evidente",
    rf_sub: "Estas situações são raras e graves. Na maioria dos casos, nenhuma se aplica.",
    rf_nenhuma: "Nenhuma se aplica, continuar",
    rf_toque: "Se alguma destas estiver a acontecer agora, toque nela:",

    qx_titulo: "O que sente?",
    qx_sub: "Escolha a queixa principal — ou descreva-a por palavras suas.",
    qx_pesquisa_label: "Escreva o que sente",
    qx_pesquisa_placeholder: "Por exemplo: dói-me a barriga",
    qx_sugestao: "Sugestão",
    qx_sem_sugestoes:
      "Não reconhecemos essas palavras. Escolha a queixa na lista abaixo.",

    fases: { 1: "Perguntas gerais", 2: "Perguntas específicas", 3: "Avaliar a gravidade" },
    fase_de: (fase, nome) => `Fase ${fase} de 3: ${nome}`,
    pergunta_n: (n) => `Pergunta ${n}`,
    sim: "Sim",
    nao: "Não",
    voltar_pergunta: "Voltar à pergunta anterior",

    res_rotulo: "Prioridade estimada",
    res_resumo: "Ver as respostas que deu",
    res_resumo_dica: "Enganou-se nalguma? Recomece e responda de novo.",
    res_aviso:
      "Esta é uma <strong>estimativa de orientação</strong>. A cor final é sempre atribuída pela triagem oficial na unidade de saúde.",
    res_112: "Ligar 112 agora",
    res_ver_urgencia: "Ver a urgência mais próxima",
    res_onde: "Onde devo ir?",

    loc_obter: "A obter a sua localização…",
    loc_permitir: 'Se o navegador pedir permissão, escolha "Permitir".',
    loc_sem_suporte: "O seu dispositivo não suporta localização automática.",
    loc_falhou:
      "Não conseguimos obter a sua localização. Pode ativá-la nas permissões do navegador (ícone junto ao endereço) e tentar de novo, ou escolher o concelho.",
    loc_alterar:
      "Escolha o concelho onde está, ou tente de novo a localização automática.",
    loc_titulo: "Em que concelho está?",
    loc_aria_concelho: "Concelho",
    loc_usar: "Usar este concelho",
    loc_gps: "Tentar localização de novo",

    enc_titulos: {
      ligar_112: "Ligue 112",
      ir_unidade: "Vá a esta unidade",
      contactar_sns24: "Ligue ao SNS 24",
      autocuidado: "Pode cuidar-se em casa",
    },
    enc_recomendacao: "Recomendação",
    enc_calculo: (hora, dia) =>
      `Cálculo feito às ${hora}${dia ? ` (${dia})` : ""}. Os estados de aberto ou fechado referem-se a esse momento.`,
    loc_usada_prefixo: "Localização usada: ",
    loc_usada_concelho: (rotulo) => `concelho de ${rotulo} (escolhido por si)`,
    loc_usada_auto: (precisao) =>
      `automática${precisao ? `, precisão aprox. ${precisao}` : ""}`,
    alterar_local: "Alterar localização",
    aviso_precisao:
      "Num computador, a localização é estimada pela ligação à internet e pode indicar o Funchal mesmo que esteja noutro concelho. Se não estiver correta, altere-a.",
    faixa_demo: (hora) => `Modo de demonstração. Hora simulada: ${hora}`,

    ac_ligar_sns: "Ligar SNS 24 (808 24 24 24)",
    ac_alerta_titulo: "Procure ajuda se:",
    alt_titulo: "Alternativas",
    alt_aberto: "aberto",
    alt_fechado: "fechado",
    direcoes: "Direções",
    persistir_titulo: "Se os sintomas persistirem",
    persistir_texto:
      "Nos próximos dias, pode dirigir-se ao seu centro de saúde. Pode ser necessária marcação prévia, por isso é boa ideia ligar antes.",
    contactos_titulo: "Contactos úteis",
    ct_emergencia: "Emergência médica",
    ct_sns: "SNS 24, aconselhamento",
    imprimir: "Imprimir ou guardar em PDF",
    nova_avaliacao: "Fazer nova avaliação",
    qr_titulo: "Navegar no telemóvel",
    qr_dica: "Aponte a câmara do telemóvel ao código para abrir as direções no Google Maps.",
    esp_linha: (te) => {
      const rotulo =
        te.ambito === "cor" ? "Espera para a sua cor" : "Tempo de espera agora";
      const partes = [];
      if (te.minutos != null) partes.push(`~${te.minutos} min`);
      if (te.em_espera != null)
        partes.push(`${te.em_espera} ${te.em_espera === 1 ? "pessoa" : "pessoas"} em espera`);
      return `${rotulo}: ${partes.join(" · ") || "sem dados"}`;
    },
    esp_curto: "de espera",
    esp_atualizado: (hora) => `Tempos de espera do SESARAM, atualizados às ${hora}`,
    esp_desatualizado: "(podem estar desatualizados)",
    esp_indisponivel: "Tempo de espera do SESARAM indisponível neste momento.",

    un_tipo: { hospital: "Hospital", centro_saude: "Centro de saúde" },
    un_servico: {
      urgencia_polivalente: "Urgência",
      urgencia_basica: "Urgência básica",
      atendimento_urgente: "Atendimento urgente",
      consulta_aberta: "Consulta / atendimento",
    },
    un_aberta: "Aberto agora",
    un_fechada: "Fechado agora",
    un_km: (km) => `a ${km} km (em linha reta)`,
    un_reconfirmar: "Dados por reconfirmar (ver nota acima).",
    un_ligar: (tel) => `Ligar ${tel}`,
    un_gmaps: "Abrir direções no Google Maps",

    mapa_indisponivel: "Mapa indisponível (sem ligação ao serviço de mapas).",
    mapa_voce: "A sua localização",
    mapa_aprox: (rotulo) => `Localização aproximada (concelho de ${rotulo})`,
  },

  en: {
    topo_sub: "Guidance for patients in the Autonomous Region of Madeira · prototype",
    rodape_aviso:
      '<strong>Notice:</strong> this tool gives general guidance and ' +
      '<strong>does not replace</strong> assessment by a health professional ' +
      'or the triage done at the emergency department. In an emergency, call ' +
      '<a href="tel:112">112</a>. Advice line: SNS&nbsp;24, ' +
      '<a href="tel:808242424">808&nbsp;24&nbsp;24&nbsp;24</a>.',
    rodape_nota:
      "Academic prototype, version 0.8. Rules and unit data pending validation with SESARAM.",
    lingua_aria: "Mudar para português",

    a_carregar: "Loading",
    erro_titulo: "Something went wrong",
    erro_ajuda:
      "If the problem persists and you need help, call SNS 24 (808 24 24 24) or, in an emergency, 112.",
    tentar_novamente: "Try again",
    recomecar_inicio: "Start over",
    recomecar: "Start over",
    aviso_importante: "Important: ",

    inicio_titulo: "Not sure if you should go to the emergency department?",
    inicio_lead:
      "Answer simple questions about how you feel and we will suggest the estimated priority and the right health unit near you. It takes about a minute.",
    passo1_t: "Emergency signs",
    passo1_d: "First we check this is not a 112 situation.",
    passo2_t: "Questions about how you feel",
    passo2_d: "Yes or no answers, in plain language.",
    passo3_t: "Recommendation",
    passo3_d: "The estimated priority and a suitable unit that is open.",
    comecar: "Start",
    selo_privacidade:
      "We store none of your data. Your answers disappear when you close the page.",

    rf_titulo: "First, obvious emergency situations",
    rf_sub: "These situations are rare and serious. In most cases, none applies.",
    rf_nenhuma: "None applies, continue",
    rf_toque: "If any of these is happening right now, tap it:",

    qx_titulo: "What are you feeling?",
    qx_sub: "Choose the main complaint — or describe it in your own words.",
    qx_pesquisa_label: "Describe what you feel",
    qx_pesquisa_placeholder: "For example: my stomach hurts",
    qx_sugestao: "Suggestion",
    qx_sem_sugestoes:
      "We did not recognise those words. Please choose a complaint from the list below.",

    fases: { 1: "General questions", 2: "Specific questions", 3: "Assessing severity" },
    fase_de: (fase, nome) => `Phase ${fase} of 3: ${nome}`,
    pergunta_n: (n) => `Question ${n}`,
    sim: "Yes",
    nao: "No",
    voltar_pergunta: "Back to the previous question",

    res_rotulo: "Estimated priority",
    res_resumo: "See the answers you gave",
    res_resumo_dica: "Got one wrong? Start over and answer again.",
    res_aviso:
      "This is a <strong>guidance estimate</strong>. The final colour is always assigned by the official triage at the health unit.",
    res_112: "Call 112 now",
    res_ver_urgencia: "See the nearest emergency department",
    res_onde: "Where should I go?",

    loc_obter: "Getting your location…",
    loc_permitir: 'If the browser asks for permission, choose "Allow".',
    loc_sem_suporte: "Your device does not support automatic location.",
    loc_falhou:
      "We could not get your location. You can enable it in the browser permissions (icon next to the address) and try again, or choose the municipality.",
    loc_alterar:
      "Choose the municipality where you are, or try automatic location again.",
    loc_titulo: "Which municipality are you in?",
    loc_aria_concelho: "Municipality",
    loc_usar: "Use this municipality",
    loc_gps: "Try location again",

    enc_titulos: {
      ligar_112: "Call 112",
      ir_unidade: "Go to this unit",
      contactar_sns24: "Call SNS 24",
      autocuidado: "You can look after yourself at home",
    },
    enc_recomendacao: "Recommendation",
    enc_calculo: (hora, dia) =>
      `Calculated at ${hora}${dia ? ` (${dia})` : ""}. Open or closed statuses refer to that moment.`,
    loc_usada_prefixo: "Location used: ",
    loc_usada_concelho: (rotulo) => `municipality of ${rotulo} (chosen by you)`,
    loc_usada_auto: (precisao) =>
      `automatic${precisao ? `, approx. accuracy ${precisao}` : ""}`,
    alterar_local: "Change location",
    aviso_precisao:
      "On a computer, location is estimated from your internet connection and may point to Funchal even if you are in another municipality. If it is wrong, change it.",
    faixa_demo: (hora) => `Demonstration mode. Simulated time: ${hora}`,

    ac_ligar_sns: "Call SNS 24 (808 24 24 24)",
    ac_alerta_titulo: "Seek help if:",
    alt_titulo: "Alternatives",
    alt_aberto: "open",
    alt_fechado: "closed",
    direcoes: "Directions",
    persistir_titulo: "If symptoms persist",
    persistir_texto:
      "Over the next few days, you can go to your health centre. An appointment may be required, so it is a good idea to call first.",
    contactos_titulo: "Useful contacts",
    ct_emergencia: "Medical emergency",
    ct_sns: "SNS 24, advice line",
    imprimir: "Print or save as PDF",
    nova_avaliacao: "New assessment",
    qr_titulo: "Navigate on your phone",
    qr_dica: "Point your phone's camera at the code to open directions in Google Maps.",
    esp_linha: (te) => {
      const rotulo =
        te.ambito === "cor" ? "Wait for your colour" : "Current waiting time";
      const partes = [];
      if (te.minutos != null) partes.push(`~${te.minutos} min`);
      if (te.em_espera != null)
        partes.push(`${te.em_espera} ${te.em_espera === 1 ? "person" : "people"} waiting`);
      return `${rotulo}: ${partes.join(" · ") || "no data"}`;
    },
    esp_curto: "wait",
    esp_atualizado: (hora) => `SESARAM waiting times, updated at ${hora}`,
    esp_desatualizado: "(may be out of date)",
    esp_indisponivel: "SESARAM waiting time unavailable right now.",

    un_tipo: { hospital: "Hospital", centro_saude: "Health centre" },
    un_servico: {
      urgencia_polivalente: "Emergency department",
      urgencia_basica: "Basic emergency unit",
      atendimento_urgente: "Urgent care",
      consulta_aberta: "Consultation / walk-in",
    },
    un_aberta: "Open now",
    un_fechada: "Closed now",
    un_km: (km) => `${km} km away (straight line)`,
    un_reconfirmar: "Data pending reconfirmation (see note above).",
    un_ligar: (tel) => `Call ${tel}`,
    un_gmaps: "Open directions in Google Maps",

    mapa_indisponivel: "Map unavailable (no connection to the map service).",
    mapa_voce: "Your location",
    mapa_aprox: (rotulo) => `Approximate location (municipality of ${rotulo})`,
  },
};
