# Integração — estado, potencial e questões em aberto

Este documento descreve como o protótipo "Onde Ir" está preparado para
integrar com os sistemas do SESARAM, distingue o que já está funcional do
que depende de definições institucionais, e enumera os problemas técnicos
ainda por resolver. Serve de referência técnica para uma futura fase de
integração.

Data de referência do protótipo: **2026-07-07**. As questões em aberto
listadas no fim refletem o que era desconhecido nesta data.

## Princípio de integração

A aplicação foi desenhada para ser consumível por outros sistemas sem
depender de nenhum deles em particular. Em vez de acoplar o protótipo a uma
plataforma específica, garantem-se duas propriedades que servem qualquer
sistema de destino:

1. **API REST/JSON *stateless*.** Não há sessão nem estado guardado no
   servidor: cada pedido carrega o seu próprio contexto. Qualquer sistema
   capaz de fazer pedidos HTTP e ler JSON consegue consumir a triagem, o
   encaminhamento e os dados das unidades.
2. **Artefacto portável (PDF).** O resumo de orientação é gerado em PDF, o
   formato que praticamente qualquer sistema consegue apresentar, anexar ou
   arquivar sem integração dedicada.

Com estas duas peças, integrar passa a ser uma escolha do lado do SESARAM
(que endpoint invocar, ou onde colocar o PDF), sem reescrever a aplicação.

## Estado atual da preparação

Já disponível e testado:

- API documentada automaticamente em `/docs` (OpenAPI).
- Triagem e encaminhamento acessíveis por HTTP, incluindo uma chamada única
  combinada (`POST /api/integracao/triagem`).
- Exportação do resumo em PDF, em binário (`POST /api/exportar_pdf`) e em
  base64 dentro de JSON (`POST /api/exportar_pdf_base64`), para o caso de um
  sistema preferir receber o documento embutido numa resposta.
- CORS aberto em desenvolvimento (a restringir ao domínio real em produção).

## Padrões de integração possíveis

Do mais simples para o mais profundo:

- **A) Ligação ou embebição (iframe).** O sistema de destino abre a
  aplicação tal como está, por hiperligação ou embebida. Não exige
  alterações. É o padrão mais comum e de menor custo.
- **B) Consumo da API.** O sistema de destino invoca os endpoints e
  apresenta o resultado na sua própria interface. Exige que esse sistema
  saiba fazer pedidos HTTP e interpretar JSON.
- **C) Anexação do PDF.** O sistema de destino recebe o resumo em PDF (por
  descarregamento ou em base64) e arquiva-o. Exige definir a que registo o
  documento fica associado e as regras clínicas e de privacidade aplicáveis.

Nota sobre o padrão C: um documento só integra um processo clínico se
cumprir requisitos que não são técnicos (relevância clínica, identificação
inequívoca do utente, responsável pelo registo, regras de acesso). O
protótipo, por opção de desenho, **não capta identificação**; o PDF inclui
um espaço de preenchimento manual. Elevar o documento a registo clínico
oficial é uma decisão institucional, não uma funcionalidade que se ativa.

## Potencial da integração

Uma triagem digital orientada ao utente, integrada no ecossistema clínico,
abre várias possibilidades concretas:

- **Pré-triagem que acompanha o utente.** O utente responde antes de chegar
  à unidade e apresenta o resumo (cor sugerida, respostas, sinais de alarme,
  hora). A triagem presencial ganha contexto e reduz-se a repetição de
  perguntas.
- **Continuidade de cuidados.** Em transferências entre unidades ou entre
  ilhas, o resumo pode acompanhar o utente como documento de contexto.
- **Redução de deslocações desnecessárias.** O encaminhamento por cor,
  proximidade e horário orienta situações pouco urgentes para o centro de
  saúde ou para autocuidado, aliviando a urgência hospitalar.
- **Indicadores agregados e anónimos.** Sem guardar dados pessoais, é
  possível recolher estatísticas de uso (queixas mais frequentes, cores
  atribuídas) úteis para planeamento.

Estas possibilidades pressupõem decisões institucionais e validação clínica;
são potencial, não estado atual.

## Referência da API

Base local: `http://127.0.0.1:8000`. Documentação interativa: `/docs`.
A API é *stateless*.

### Núcleo

| Método | Caminho | Função |
| --- | --- | --- |
| GET  | `/api/saude` | Estado e versão do serviço. |
| GET  | `/api/queixas` | Queixas disponíveis. |
| GET  | `/api/queixas/sugerir?q=` | Sugestões a partir de texto livre (sinónimos). |
| GET  | `/api/red-flags` | Sinais de emergência (avaliados primeiro). |
| GET  | `/api/fluxogramas?idioma=pt\|en` | Fluxogramas Mermaid das regras atuais, relidos do disco (v0.12). |
| POST | `/api/triagem` | Próxima pergunta ou resultado (cor). |
| GET  | `/api/unidades` | Todas as unidades. |
| GET  | `/api/unidades/proxima?lat=&lng=` | Unidades mais próximas de um ponto. |
| GET  | `/api/espera` | Tempos de espera das urgências. |
| POST | `/api/encaminhamento` | Destino recomendado, dada cor + localização. |
| GET  | `/api/contactos` | 112 e SNS 24. |
| GET  | `/api/feriados?ano=` | Feriados considerados nos horários. |

### Endpoints orientados a integração

**`POST /api/integracao/triagem`** — triagem e encaminhamento numa só
chamada. Envia-se a queixa e as respostas disponíveis; recebe-se a próxima
pergunta enquanto faltarem respostas, ou o resultado (e o encaminhamento, se
`lat`/`lng` forem fornecidos).

Pedido:
```json
{ "queixa": "dor_abdominal",
  "respostas": { "ab_q1": "sim", "ab_q2": "nao" },
  "lat": 32.65, "lng": -16.91 }
```
Resposta (cor determinada):
```json
{ "tipo": "resultado",
  "queixa": "dor_abdominal",
  "resultado": { "cor": "amarelo", "cor_info": {} },
  "encaminhamento": { "acao": "ir_unidade", "unidade": {}, "alternativas": [] } }
```
Resposta (faltam respostas):
```json
{ "tipo": "pergunta", "queixa": "dor_abdominal", "pergunta": {} }
```

**`POST /api/exportar_pdf`** — resumo de orientação em PDF
(`application/pdf`). O corpo é o que o utente viu; o servidor desenha o
documento.

**`POST /api/exportar_pdf_base64`** — o mesmo PDF embutido em JSON
(`{ "pdf_base64": "..." }`).

## Privacidade

- O protótipo não guarda dados pessoais no servidor e não pede
  identificação. Isto mantém-no fora do âmbito mais exigente do RGPD
  enquanto é uma ferramenta de orientação.
- O histórico de avaliações do utente é guardado **apenas no dispositivo**
  (armazenamento local do navegador), não é enviado para nenhum servidor, e
  pode ser apagado pelo utente a qualquer momento.
- Se, numa fase de integração, o PDF passar a conter identificação e for
  anexado a um processo, passa a existir tratamento de dados de saúde
  (categoria especial), com as exigências associadas (base legal, HTTPS,
  autenticação, controlo de acessos), a definir do lado da integração.
- **Sem scripts de terceiros em execução (desde a v0.12).** As
  bibliotecas de frontend (Mermaid, Leaflet, gerador de QR) estão
  vendorizadas em `static/vendor/` e servidas pelo próprio serviço — a
  app não vai buscar código a CDNs externos ao abrir. Isto é relevante
  numa rede hospitalar, onde o acesso a domínios externos é
  frequentemente bloqueado: a app funciona sem essas exceções. Os únicos
  pedidos externos que restam são os tiles do mapa (CARTO) e as Google
  Fonts, ambos com degradação graciosa; se a política de rede os
  bloquear, a app mantém-se utilizável (tipos de letra do sistema, sem
  mapa de fundo), e podem ser igualmente alojados internamente se for
  requisito.

## Problemas técnicos em aberto

1. **Validação clínica das regras de triagem.** As árvores de decisão e os
   textos de autocuidado são exemplos e requerem validação por um
   profissional de triagem antes de qualquer uso real. É o requisito
   crítico. (Ver `docs/validacao_clinica.html`.)
2. **Origem dos tempos de espera.** Os tempos são atualmente obtidos por
   recolha automática (*scraping*) das páginas públicas do SESARAM, o que é
   frágil a alterações do site. Uma API oficial seria a solução robusta.
3. **Confirmação dos dados das unidades.** Moradas, telefones, horários e
   coordenadas foram sendo confirmados progressivamente; os registos ainda
   por confirmar estão marcados com `dados_confirmados: false`.
4. **Tempo de viagem real.** Desde a v0.11, os tempos de viagem vêm de uma
   rede calibrada de estradas da RAM (`app/data/rede_viagem.json`), local e
   editável, sem enviar coordenadas de utentes para fora. É um modelo
   simplificado e, como tal, tem casos em que ordena mal duas unidades
   próximas: por exemplo, a partir do sítio da Achada da Rocha (Gaula), o
   modelo estima o CS da Camacha como ligeiramente mais rápido do que o CS
   de Gaula, quando na prática é o contrário. A causa é estrutural (o
   modelo trata os acessos locais por escalões de velocidade em função da
   distância, e a fronteira entre escalões pode inverter a ordem de dois
   destinos vizinhos), pelo que afinar troços resolve casos pontuais mas
   não a classe de erro. Numa implementação a sério há três caminhos, por
   ordem crescente de fidelidade e de custo:

   1. **OSRM alojado pela instituição** (motor de rotas em código aberto
      sobre dados OpenStreetMap). O protótipo já o suporta: basta definir
      a variável de ambiente `VIAGEM_OSRM_URL`, com recuo automático para
      a rede calibrada em caso de falha. É leve (um contentor Docker com o
      extrato OSM da Madeira), corre dentro da rede do SESARAM (nenhuma
      coordenada de utente sai para terceiros) e resolve a classe de erro
      acima, porque calcula rotas sobre o grafo real de estradas. É a
      opção recomendada para piloto. Usar o servidor público de
      demonstração do OSRM está fora de questão em produção: implicaria
      enviar a localização de doentes para terceiros (RGPD) e não tem
      garantias de disponibilidade. Alojar internamente é uma decisão dos
      serviços de informática, com manutenção e atualização periódica do
      mapa incluídas. Trânsito em tempo real fica, mesmo assim, por
      cobrir.

   2. **API comercial de rotas, recomendada para produção.** Se o projeto
      avançar a sério, o ideal é usar a **Google Routes API** (ou a
      Distance Matrix, da mesma família) ou um serviço equivalente (Azure
      Maps, Mapbox). São serviços pagos, mas dão tempos de viagem com
      trânsito real, mapas mantidos profissionalmente e SLA, isto é,
      exatamente a qualidade que um utente espera quando a aplicação lhe
      diz "está a 7 minutos de carro". O custo por pedido é baixo e o
      volume deste caso de uso é modesto (um punhado de pares
      origem-destino por triagem, com cache agressiva por zona). A
      contrapartida é que as coordenadas do utente são enviadas a um
      terceiro, pelo que esta via **exige avaliação prévia de proteção de
      dados** (RGPD) com o encarregado de proteção de dados da
      instituição: base legal, contrato de subcontratação, minimização
      (por exemplo, arredondar coordenadas de origem à zona) e informação
      ao utente.

   3. **Tabela de tempos por estrada, como paliativo (implementada na
      v0.11.3).** Sem infraestrutura nem orçamento, a rede calibrada
      mantém-se e um ficheiro editável (`app/data/tempos_medidos.json`)
      guarda tempos por estrada consultados antes do modelo, por zona e
      com âncoras num raio curto. Preenche-se automaticamente com um
      motor de rotas de dados abertos
      (`scripts/calcular_tempos_medidos.py`, OpenRouteService ou OSRM)
      ou à mão no Google Maps para conferir pares suspeitos
      (`scripts/tempos_medidos_relatorio.py --links` e
      `--divergencias`). Resolve casos como Achada da Rocha →
      Gaula/Camacha, mas envelhece à medida que a rede viária muda e a
      qualidade fica abaixo de um serviço com trânsito, pelo que deve
      ser encarado como remendo temporário e não como solução: remove-se
      apagando o ficheiro (ou com `VIAGEM_TEMPOS_MEDIDOS=0`), e a
      aplicação volta sozinha à rede calibrada.
5. **Identidade institucional.** As cores e o logótipo são provisórios (os
   azuis trocam-se numa variável CSS). O texto do *disclaimer* deve seguir a
   redação institucional pretendida.

## Questões a apurar sobre a plataforma interna de destino

À data de referência acima, não estava documentado, do lado deste protótipo,
o comportamento da plataforma de desenvolvimento interna do SESARAM que
serviria de destino a uma integração. Estas questões devem ser esclarecidas
com a equipa de informática do SESARAM antes de desenhar a integração:

1. A plataforma consome APIs REST/JSON? Executa JavaScript? Como apresenta
   ou anexa documentos?
2. Com que sistemas clínicos comunica e como associa documentos a um
   episódio ou registo?
3. Qual o ponto de integração pretendido para uma ferramenta orientada ao
   **utente**: um portal do utente já existente, ou uma ferramenta interna
   de profissionais? (São públicos-alvo distintos.)
4. Dos três padrões acima (ligação/iframe, consumo de API, anexação de PDF),
   qual é compatível e preferido?
5. Existe API oficial para os tempos de espera das urgências, ou a recolha
   automática é aceitável nesta fase?
6. Quais os requisitos de identidade institucional e de privacidade a
   respeitar desde já?
