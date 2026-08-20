# Histórico de versões

O histórico completo do protótipo, do mais recente para o mais antigo.
O README guarda apenas um apontador para aqui, de propósito: este
ficheiro pode crescer, o README não. (English version: `CHANGELOG.md`.)

As versões anteriores à v0.5 são anteriores a este registo — o motor de
triagem inicial, a validação no arranque e o calendário de feriados
(v0.4) — e os detalhes vivem no histórico do git.

## v0.16.2 — robustez: erros legíveis, limites anti-abuso, fontes locais, contrato da API

Segunda ronda da revisão externa ao estilo "engenheiro sénior exigente"
(a primeira deu a v0.16.1): cinco melhorias de robustez, todas
verificadas por testes novos, sem tocar na lógica clínica.

- **Erros de dados legíveis de ponta a ponta (o bug real desta ronda).**
  O erro de SINTAXE num JSON de regras — o engano mais provável de quem
  edita à mão — era o único que escapava às mensagens amigáveis:
  rebentava com um traceback cru no arranque (sem dizer o ficheiro na
  mensagem) e com um `500 Internal Server Error` em `/api/fluxogramas`,
  apesar de a docstring prometer a mensagem no campo `"erro"`
  (reproduzido na revisão com um `{` a mais num ficheiro real). O
  `_carregar` do motor passa a converter `json.JSONDecodeError`/`OSError`
  em `RuntimeError` com o NOME do ficheiro — o mesmo formato das
  validações existentes — e o endpoint volta a cumprir a promessa. De
  caminho, mais dois enganos da mesma família ganharam mensagens claras:
  raiz que não é um objeto JSON e fluxo sem `"id"` no topo (antes:
  `AttributeError`/`KeyError` crus).
- **Limites de sanidade nos pedidos (anti-abuso).** Um único
  `POST /api/exportar_pdf` artesanal custava **~33 segundos de CPU**
  (medido na revisão): num endpoint público, sem autenticação, meia
  dúzia de pedidos assim deitavam o servidor abaixo. Entram três camadas,
  da mais barata para a mais profunda: (1) um teto ao tamanho do corpo
  dos pedidos — middleware ASGI em `app/main.py`, `413` cedo, 1 MB por
  omissão, configurável por `ONDE_IR_CORPO_MAXIMO`; (2) máximos em todos
  os campos de texto e de lista dos schemas (`app/models/schemas.py`),
  folgados face aos dados reais (o maior fluxo tem ~40 discriminadores,
  a maior mensagem ~700 caracteres) para nenhum pedido legítimo mudar;
  (3) o próprio gerador de PDF apara o que desenha (`_aparar`, tetos em
  `pdf_clinico.py`), para a propriedade valer mesmo para quem lhe chamar
  diretamente. O mesmo ataque passa a custar ~0,03 s.
- **Public Sans embutida (offline + RGPD).** A fonte vinha do Google
  Fonts em runtime — a única chamada a um CDN que restava, em contradição
  com o "funciona offline" (Leaflet, Mermaid e o QR já viviam em
  `static/vendor` exatamente para isso) e com a postura de privacidade:
  carregar fontes da Google envia o IP de cada utente a um terceiro. Os
  quatro pesos usados pela interface (400/600/700/800, woff2) passam a
  viver em `static/vendor/public-sans/`, com a licença (SIL OFL 1.1) ao
  lado, vindos da release oficial v2.001 do U.S. Web Design System. Fica
  também aberto o caminho para uma Content-Security-Policy estrita.
- **Formato de resposta documentado em `/docs` (contrato completo).** Os
  endpoints devolviam `dict`, por isso a documentação interativa mostrava
  os pedidos mas não as respostas — meio contrato, logo no argumento de
  integração. `/api/triagem`, `/api/encaminhamento` e
  `/api/integracao/triagem` passam a declarar `response_model`
  (`app/models/respostas.py`, novo), com duas decisões deliberadas para
  documentar sem partir: `extra="allow"` (uma chave nova do routing nunca
  é silenciosamente apagada da resposta) e `response_model_exclude_unset`
  (as chaves que o routing não põe continuam AUSENTES no fio, não
  `null`). Testes fixam o formato nos dois sentidos: a `politica`
  continua a não aparecer no verde e a aparecer no amarelo.
- **Matriz de CI 3.11+3.12 e licença.** O README promete "Python 3.11+"
  mas o CI só testava o 3.12; a matriz passa a testar os dois
  (`fail-fast` desligado, para ver as duas quando uma parte). E o
  repositório não tinha licença: entra `LICENSE` (MIT) na raiz — com o
  titular dos direitos assinalado como por confirmar entre o autor e o
  SESARAM — e uma secção «Licença» nos dois READMEs a delimitar o que a
  licença do código NÃO cobre: o conteúdo clínico da tabela de Manchester
  (licenciado pelo Grupo Português de Triagem) e os vendors, cada um com
  a sua licença ao lado.

Os catorze testes novos vivem em `tests/test_v16_2.py`.

## v0.16.1 — endurecer o PDF, lint no CI, dependências fixadas

Versão de correção, guiada por uma revisão de código externa ao estilo
"engenheiro sénior exigente". Sem funcionalidades novas: três frentes de
acabamento, por ordem de importância.

- **Injeção de markup no PDF corrigida (o bug real).** O `Paragraph` do
  reportlab interpreta um mini-HTML, e o `pdf_clinico.py` entregava-lhe
  texto do pedido sem escapar: uma mensagem com `<b>` solto rebentava a
  geração (500), uma tag `<img>` fazia o servidor tentar abrir um
  ficheiro, e uma entidade inválida (`&#xZZ;`) também dava 500. Agora
  TODO o texto vindo de fora passa por `_esc()` (escape de `<`, `>`,
  `&` e aspas) antes de chegar ao reportlab; só o markup escrito pelo
  próprio módulo é interpretado. Dez testes novos
  (`tests/test_pdf_escape.py`) fixam o comportamento: os pedidos
  hostis têm de devolver um PDF válido E mostrar o texto literalmente
  (escapar não é apagar).
- **Números e ligações da documentação a dizer a verdade.** Os badges e
  o texto dos READMEs estavam dessincronizados (370/341 testes "à data
  da v0.15.3", "última versão v0.13.1"); passam a refletir a suite real
  e esta versão. As referências a `docs/adr/0012-logging.md` e
  `docs/adr/0011-divisao-routing.md` (numeração antiga) apontam agora
  para os ficheiros que existem: `0011-logging.md` e
  `0010-divisao-routing.md`.
- **Lint e formato no CI; dependências fixadas.** O `ruff` e o
  `black --check` entram no `ci.yml` (configuração no `pyproject.toml`
  novo; versões em `requirements-dev.txt`) — um F811 teria acusado a
  `_primeira_aberta` definida duas vezes em `routing.py`, agora
  apagada, e os imports a meio do ficheiro subiram para o topo. Todo o
  código foi formatado com o black (mudança mecânica; a suite valida
  que nada se alterou). O `requirements.txt` passa a fixar as versões
  exatas testadas, para builds reprodutíveis.

## v0.16.0 — o frontend "aplicação de saúde"

Uma entrega só de interface. O ponto de partida foi uma análise de UX/UI
externa (gerada por um assistente de IA) com vinte sugestões; esta versão
é a leitura CRÍTICA dessa análise, não a aplicação cega. **Nenhum texto
clínico muda**: perguntas, conselhos e regras ficam intactos nos dados
(têm o seu próprio circuito de validação, e reescrever 1187 perguntas é
exatamente onde o significado derraparia). O que muda é a apresentação.

O que a análise acertou (e entrou):

- **Sim/Não gigantes.** Os botões de resposta passam a blocos de 88px
  com ícones de visto/cruz e peso 800 — a resposta É o ecrã. Ficam
  deliberadamente NEUTROS: na triagem, "sim" costuma significar pior, e
  pintar o "sim" de verde daria o sinal errado. Ao tocar, o botão
  confirma-se visualmente um instante antes de a próxima pergunta entrar
  (e os dois inativam-se contra toques duplos); com movimento reduzido
  no sistema, avança já.
- **Barra de progresso — mas honesta.** A sugestão era "8 / 12
  perguntas"; esse número exato é impossível de prometer, porque a
  avaliação pode terminar mais cedo consoante as respostas. O que se
  mostra é "Pergunta N · no máximo M" (o máximo real do fluxo, que a API
  já enviava) com uma barra que enche até esse máximo — responde ao
  "faltam 2 ou faltam 30?" sem mentir nem explicar a mecânica de fim
  antecipado (explicá-la enviesaria respostas).
- **Página inicial de aplicação.** Título de capa, UM botão enorme
  ("Iniciar avaliação") e o resto em segundo plano: os três passos
  recolhem-se em "Como funciona?", e entram dois atalhos de contacto
  (112 e SNS 24, os mesmos do rodapé) porque quem chega em pânico não
  devia ter de fazer scroll. A sugestão original pedia MAIS opções na
  página inicial ("ver unidades", etc.), o que contradiz o seu próprio
  princípio de um objetivo por ecrã — não entrou.
- **Resultado como cartão.** A guia de prioridade é agora o
  elemento-assinatura: fundo tingido na cor da triagem, lombada na cor,
  a forma acessível + nome da cor no rótulo, classificação em destaque
  num cartão compacto e o tempo-alvo numa pílula com relógio. Abre com "Com base nas
  suas respostas:", em vez de parecer um campo de base de dados. As
  tintas e as cores de texto por nível foram calculadas para cumprir a
  WCAG (o auditor verifica cada valor de `--cor-texto`).
- **Cartão da unidade com estatísticas.** Os três números que decidem a
  ida — tempo de carro, espera e estado — sobem de chips para blocos de
  estatística (número grande, rótulo pequeno, nota "estim./registado").
  Os chips ficam como segunda linha de contexto (km por estrada, pessoas
  em espera). A morada ganha ícone; os horários recolhem-se num acordeão
  que abre sozinho quando a unidade está fechada (é quando interessam).
- **Mapa em acordeão, aberto por defeito.** A sugestão era escondê-lo
  atrás de "Ver no mapa"; entrou o acordeão, mas ABERTO à partida (ver
  logo onde fica a unidade ajuda mais do que esconder o mapa), com
  "Ocultar o mapa" para quem preferir o ecrã curto. A preferência
  sobrevive à troca de língua e o Leaflet arranca apenas dentro do
  acordeão, nunca no corpo do render do ecrã.
- **Hierarquia, espaçamento e microinterações.** Escala tipográfica com
  peso 800 nos títulos e na pergunta, mais ar entre cartões, cantos de
  16px, sombras discretas POR CIMA dos contornos visíveis (os contornos
  ficam: são a acessibilidade de quem tem sensibilidade ao contraste
  reduzida), transições curtas — tudo desligado com
  `prefers-reduced-motion`.
- **Ícones, sem emojis.** O conjunto SVG de traço único cresce (visto,
  cruz, telefone, mapa, escudo) para respostas, atalhos, contactos e o
  acordeão do mapa. Emojis não entram: variam por sistema e destoam num
  contexto clínico.

O que a análise já não sabia (e por isso não mudou):

- As perguntas JÁ são leigas desde a v0.14.1 (`texto_utente`), o "Porquê
  esta recomendação?" JÁ existe desde a v0.13.1, os tempos JÁ aparecem
  como "~18 min", e a interface JÁ é neutra fora do resultado (decisão
  da v0.14.1, mantida: nenhuma cor de Manchester durante as perguntas).
- Um "ecrã de resumo" à parte duplicaria o cartão de destino; o núcleo
  útil da ideia entrou como pílula de contexto: a prioridade (forma +
  cor + classificação) acompanha a pessoa até ao ecrã de encaminhamento.

Mais na mesma entrega:

- **Lista de queixas agrupada.** "Adultos e situações gerais" e "Bebés e
  crianças", pela flag `pediatrico` que a API já enviava — pais em
  stress deixam de varrer 56 cartões misturados. A pesquisa continua
  acima de tudo.
- **Ouvir a pergunta.** O botão de leitura em voz alta (v0.15.1) chega
  ao ecrã da pergunta, com a mesma Web Speech API local.
- **Contactos com ícone** e a marca com símbolo no topo.
- Testes novos em `tests/test_v16.py` fixam a barra honesta, os botões
  neutros, a guia tingida, o mapa aberto por defeito em acordeão (sem
  arranque do Leaflet no render) e as chaves bilingues; o pin de cache do `test_v15_3`
  deixou de fixar o número exato (o mesmo passo que o `test_v15_2` já
  tinha dado). "112" e "SNS 24" escrevem-se na marcação, como no rodapé:
  números e marcas não são texto a traduzir, e o auditor de traduções
  continua sem exceções.

## v0.15.3 — as perguntas como dados

O espelho da v0.15.2, agora para a outra metade do conteúdo leigo: as
perguntas de triagem reescritas em linguagem do utente. Nenhum texto
mostrado ao utente muda e a lógica de triagem não mexe — muda quem
consegue editar o quê, o que fica registado, e o que parte o CI quando
alguém se engana. Com isto, deixa de haver conteúdo clínico dentro de
código Python.

- **As perguntas saem do código.** As 186 reescritas leigas (PT e EN,
  lado a lado) que cobrem os 1187 discriminadores viviam num dicionário
  em `scripts/_perguntas_utente.py`; passam para
  `app/data/perguntas_utente.json`, editável como qualquer outro
  ficheiro de dados, e o `.py` ficou reduzido a um carregador (o nome
  histórico `PERGUNTAS_UTENTE` continua a funcionar para o importador da
  tabela). Editar e aplicar **já não precisa do Excel**: o novo
  `scripts/aplicar_perguntas_utente.py` refaz só `texto_utente`/
  `texto_utente_en` em todos os ficheiros de `rules/` (o texto clínico
  fica intocado), é idempotente byte a byte e só reescreve o que mudou.
- **Estado de validação por item — que vive só no ficheiro editável.**
  Cada reescrita ganhou `validado`, `validado_por` e `validado_em`, como
  no aconselhamento, mas com uma decisão de desenho diferente: o estado
  **não é copiado** para as regras. As regras também se editam à mão, e
  uma cópia do estado lá dentro era garantia de dessincronização; o
  motor lê o `perguntas_utente.json` no arranque quando precisa dele.
- **O portão de produção reverte — não esconde.** Com
  `ONDE_IR_APENAS_VALIDADO=1`, as reescritas ainda não validadas saem
  das perguntas e o utente vê a pergunta **clínica oficial** de
  Manchester (o recuo natural do motor, que é a fonte validada).
  Esconder uma pergunta mudaria a triagem, por isso aqui a semântica do
  portão é outra: no aconselhamento esconde-se, nas perguntas
  troca-se a redação proposta pela oficial. Ficheiro em falta com o
  portão ligado = tudo revertido com aviso; ficheiro corrompido = erro
  no arranque.
- **A vista de revisão ganhou a secção das perguntas.** A página interna
  `/revisao` passou a ter duas secções (Aconselhamento | Perguntas); a
  nova mostra, por fluxo, a pergunta clínica oficial lado a lado com a
  reescrita PT/EN, a cor/prioridade e o estado de validação por item,
  com os mesmos filtros (só por validar, procurar) e dados relidos do
  disco a cada refresh (`GET /api/perguntas/revisao`, com o SHA-256 do
  ficheiro editável na resposta).
- **Verificador próprio no CI.** O novo `scripts/verificar_perguntas.py`
  exige **cobertura total** — discriminador sem entrada nas reescritas é
  erro, porque o utente veria o texto clínico sem ninguém ter decidido
  isso — e apanha reescritas editadas sem aplicar (ou regras editadas à
  mão, comparadas item a item), chaves órfãs, pares PT/EN incompletos e
  validações sem quem/quando. Lista como AVISO os textos clínicos
  repetidos dentro do mesmo fluxo (12 casos herdados da tabela oficial,
  que por construção partilham a mesma reescrita) e as colisões de
  chaves distintas na mesma frase leiga (hoje zero).
- **`marcar_validado.py`: validar sem editar JSON à mão.** Um CLI único
  para os dois ficheiros de reescritas (`aconselhamento` | `perguntas`):
  lista o que está por validar (`--listar --contem ...`), marca e
  desmarca pela chave clínica exata (espaços a mais são tolerados; chave
  errada não grava nada e sugere as parecidas), preenche os três campos
  de uma vez e reescreve o ficheiro no formato canónico — o `git diff`
  mostra só os campos tocados. No aconselhamento corre o `aplicar`
  automaticamente (para o SHA-256 em `fonte.reescritas` não ficar
  dessincronizado); nas perguntas não é preciso, porque o estado vive só
  no ficheiro editável.
- **A escolha bilingue do frontend ganhou testes.** A regra "usa o campo
  `*_en` quando a língua é inglês e ele existe; senão o português" vivia
  no `campo()` do `app.js`, sem testes. Passou para o núcleo
  (`Nucleo.textoNaLingua`, funções puras) com seis testes novos em Node
  — incluindo objetos-pergunta do motor e a garantia de nunca aparecer
  `undefined` no ecrã — e o `campo()` limita-se a injetar a língua
  ativa. São agora 14 testes Node no total.
- **Testes antigos deixaram de pinar a versão exata.** O teste do
  `index.html` (v0.15.2) exigia `?v=20` e `v0.15.2` literais, e o da
  versão exigia igualdade — cada entrega obrigava a editar testes de
  versões anteriores. Passam a fixar o que interessa (a ordem de
  carregamento do núcleo, um mínimo de versão); o número exato do
  cache-busting vive nos testes da versão corrente. A bateria soma 29
  testes novos (`tests/test_v15_3.py`), num total de 370.

Fica por fazer, de propósito: a modularização a sério do `app.js` (~1450
linhas; o núcleo continua a ser o tijolo, não a obra) e um runner de
testes JS mais completo; regressão visual e testes com leitor de ecrã
real — a página `/revisao` remodelada foi verificada por testes e à mão
na API, mas não num browser real; a reconciliação clínica autocuidado ×
aconselhamento (visível e listada desde a v0.15.2, por decidir); o
backlog de reescritas leigas do aconselhamento (~148 candidatas); e a
validação clínica em si — 0 de 85 conselhos e 0 de 186 perguntas
validados, agora com a ferramenta para registar cada aprovação.

## v0.15.2 — governação do aconselhamento e redes de segurança

Uma versão de arrumação deliberada: nenhum texto mostrado ao utente muda
(exceto os filetes, ver abaixo) e a lógica de triagem não mexe. O que
muda é quem consegue editar o quê, o que fica registado, e o que parte o
CI quando alguém se engana — as fraquezas de arquitetura e governação
identificadas na revisão da v0.15.1.

- **As frases do utente saem do código.** A coisa que a equipa clínica
  mais vai querer corrigir — as frases leigas do cartão "O que pode
  fazer" — vivia num `.py`, contra a filosofia "regras como dados". As
  85 reescritas (PT e EN, lado a lado) passam para
  `app/data/aconselhamento_utente.json`, editável como qualquer outro
  ficheiro de dados; `scripts/_aconselhamento_utente.py` ficou reduzido a
  um carregador, e os nomes históricos continuam a funcionar. Editar e
  aplicar **já não precisa do Excel**: o novo
  `scripts/aplicar_aconselhamento_utente.py` refaz só a camada do utente
  do `aconselhamento.json` (o texto clínico fica intocado), é idempotente
  byte a byte, e o importador da tabela usa exatamente a mesma função de
  fusão — uma única lógica, sem duas cópias a divergir.
- **Estado de validação clínica por item.** Cada reescrita ganhou
  `validado`, `validado_por` e `validado_em` (AAAA-MM-DD): rascunho e
  conteúdo aprovado deixam de ser indistinguíveis para o sistema. O
  verificador exige o registo completo quando `validado=true`, e o novo
  portão de produção `ONDE_IR_APENAS_VALIDADO=1` faz o motor esconder ao
  utente tudo o que ainda não estiver validado (o texto clínico continua
  a ir para os integradores). Por omissão fica desligado: em
  desenvolvimento mostra-se tudo, marcado como sujeito a validação. O
  estado atual (0 de 85 validados) ficou escrito em `docs/VALIDACAO.md`.
- **Vista de revisão do clínico (`/revisao`).** Quem revia o ecrã do
  utente não via o que o filtro de segurança esconde — não conseguia
  confirmar que o filtro acerta. A nova página interna mostra, por fluxo
  e cor, o conselho clínico lado a lado com a frase leiga PT/EN, o estado
  de validação de cada item e, a cinzento, os itens ocultos ao utente;
  com filtros (só ocultos, só por validar, procurar) e dados relidos do
  disco a cada refresh (`GET /api/aconselhamento/revisao`), como os
  fluxogramas. É a ferramenta para a sessão de validação item a item.
- **Proveniência dos dados.** O `aconselhamento.json` ganhou o bloco
  `fonte`: `fonte.tabela` regista de que Excel exato os conselhos vieram
  (nome, SHA-256, data, nº de linhas — preenchido na próxima importação;
  até lá o verificador avisa que a proveniência está por registar) e
  `fonte.reescritas` grava o SHA-256 do ficheiro editável. É este hash
  que transforma "editei as reescritas e esqueci-me de aplicar" num erro
  de CI com a instrução do que correr — e "editaram o ficheiro gerado à
  mão" também é apanhado, item a item.
- **Importadores sem lógica duplicada.** `slug()`, a normalização de
  chaves e o mapa prioridade→cor estavam definidos duas vezes
  (`importar_manchester.py` e `importar_aconselhamento.py`) e tinham de
  andar sincronizados à mão — se o `slug()` mudasse num e não no outro, o
  mapeamento fluxo↔aconselhamento partia em silêncio. Passam a viver uma
  única vez em `scripts/_manchester_comum.py`, com testes próprios; a
  `limpar()` das regras ficou local de propósito (preserva o espaçamento
  interno dos discriminadores, e o comentário explica a diferença).
- **A propriedade de segurança do frontend ganhou testes.** A garantia
  "o utente só vê itens com `texto_utente`; nunca o texto clínico" vivia
  no `app.js`, sem nenhum teste — se alguém "melhorasse" o filtro para
  recuar para o texto clínico, nada apanhava. A filtragem, a escolha da
  língua e a desduplicação saíram para `static/js/nucleo.js` (funções
  puras, sem DOM), fixadas por oito testes que correm em Node
  (`tests/js/teste_nucleo.js`), no CI e embrulhados no pytest; o
  `app.js` limita-se a pintar o que o núcleo devolve. É o primeiro passo
  — deliberadamente pequeno — da modularização do frontend.
- **Auditoria de acessibilidade no CI — e os filetes corrigidos.** O novo
  `scripts/auditar_acessibilidade.py` verifica o que é verificável sem
  browser: os rácios de contraste WCAG dos pares de cores realmente
  usados (texto ≥ 4,5:1; componentes ≥ 3:1), a língua da página, o
  viewport sem bloqueio de zoom, nomes acessíveis nos botões estáticos,
  `aria-live`, `:focus-visible`, alvos de toque ≥ 48 px e ausência de
  `tabindex` positivo. A primeira corrida confirmou a análise da
  v0.15.1: o único problema real eram os filetes (1,4:1, invisíveis para
  quem tem sensibilidade ao contraste reduzida). Com o botão de alto
  contraste removido, o tema base passou a cumprir sozinho: `--linha`
  subiu para 3,6:1 e `--linha-forte` para 5,7:1 — **é a única mudança
  visível desta versão** (filetes mais escuros), reverte-se em duas
  linhas de CSS, mas a auditoria bloqueia a regressão no CI.
- **Verificador mais completo.** Além das chaves órfãs e dos pares PT/EN,
  o `verificar_aconselhamento.py` passa a apanhar: reescritas editadas
  sem aplicar (SHA), edições à mão do ficheiro gerado, estado de
  validação incompleto e a estrutura antiga sem estado. E lista, como
  AVISO, as **sobreposições autocuidado × aconselhamento** na mesma cor
  (frases muito parecidas que podem aparecer no mesmo ecrã) — a relação
  entre os dois blocos ficou definida no guia dos dados, mas a
  reconciliação é uma decisão clínica e fica fora do CI de propósito.

Fica por fazer, de propósito: a modularização a sério do `app.js` (~1300
linhas; o núcleo é o primeiro tijolo, não a obra) e um runner de testes
JS mais completo; regressão visual e testes com leitor de ecrã real (a
auditoria estática não substitui nenhum dos dois); a reconciliação
clínica autocuidado × aconselhamento (agora visível e listada, mas por
decidir); a mesma migração "de `.py` para dados" para as perguntas do
utente (`scripts/_perguntas_utente.py`, o mesmo padrão do
aconselhamento); e o backlog de reescritas leigas que o verificador
dimensiona (~148 candidatas).

## v0.15.1 — aconselhamento mais seguro, bilingue e reordenado

Continuação da v0.15.0, agora a olhar para o cartão "O que pode fazer"
do ponto de vista de quem mais precisa dele: o doente grave, o doente
com pouca literacia ou vista fraca e o visitante que não fala português.
Mudança de interface e de salvaguardas; a lógica de triagem continua
igual.

- **A ordem deixa de estar contra o doente mais grave.** No vermelho, o
  cartão de primeira ajuda passa a vir **logo a seguir ao botão 112** (e
  já não depois do botão de recomeçar). Nas outras cores, os conselhos
  aparecem antes da navegação. O primeiro conselho de cada cor ganha
  destaque como **ação principal**, para saltar à vista sob stress.
- **Os conselhos em inglês.** Cada conselho leigo ganhou a variante
  `texto_utente_en` (mapa `ACONSELHAMENTO_UTENTE_EN`, com exatamente as
  mesmas chaves do português; frases PT iguais partilham a mesma
  tradução, para a desduplicação funcionar igual nas duas línguas). Com a
  interface em EN, o cartão "What you can do" aparece todo em inglês; se
  alguma vez faltar uma tradução, mantém-se o recuo seguro habitual
  (mostra-se o português). Tal como o texto português, as traduções são
  uma proposta sujeita a validação clínica.
- **Ler em voz alta, nas duas línguas.** Botão "Ouvir" no cartão, com a
  Web Speech API do browser (local, sem rede). Lê o que está no ecrã, na
  língua da interface: pt-PT em português, en-GB em inglês. O botão só
  aparece se o browser suportar síntese de voz; a leitura pára ao mudar
  de ecrã.
- **Os conselhos deixam de desaparecer no encaminhamento — e mudam de
  lugar.** Quem toca em "ver onde ir" mantém o cartão "O que pode
  fazer", mas agora no **fim do ecrã**, depois das unidades e dos botões
  de contacto: nesse ponto o utente já viu os conselhos no resultado, e
  o que procura primeiro é para onde ir e a quem ligar. Os botões de
  PDF, imprimir e nova avaliação fecham a página.
- **A cor da pulseira deixa de estar sozinha.** Cada nível ganha uma
  **forma distinta** antes da etiqueta de cor (círculo, triângulo,
  losango, quadrado, estrela), legível por quem tem daltonismo
  vermelho-verde (cerca de 8% dos homens).
- **Sem conselhos repetidos ao utente.** O cartão passa a desduplicar ao
  nível do texto mostrado (na língua ativa): dois conselhos clínicos
  distintos que colapsam na mesma frase leiga (por exemplo "paracetamol"
  e "paracetamol ou ibuprofeno") deixam de gerar dois pontos quase
  iguais.
- **Salvaguarda contra a falha silenciosa do mapeamento.** O
  aconselhamento leigo liga-se ao clínico pela string exata; bastava
  corrigir um espaço na tabela para um conselho desaparecer do ecrã sem
  qualquer erro. O novo `scripts/verificar_aconselhamento.py` apanha essa
  deriva (chaves órfãs = falha no CI) e imprime um relatório: cobertura,
  colisões de texto, gralhas herdadas da origem (`paracematol`,
  `cetrizina`, `analgesicos`) e a dimensão do backlog oculto (estimativa,
  por alto, de quanto é mesmo só-profissional e quanto é conselho leigo
  seguro ainda por reescrever). Com a chegada do inglês, verifica também
  que os mapas PT e EN têm as mesmas chaves, que nenhuma chave EN ficou
  órfã e que o `aconselhamento.json` está em dia (cada `texto_utente`
  com o seu `texto_utente_en`). Ligado ao `validar_dados.py` e ao CI.
  Removida, de caminho, uma chave morta ("Sinais de choque..." truncada)
  que não correspondia a nenhum conselho e nunca chegava ao utente.

Fica por fazer, de propósito (exige validação clínica e/ou é uma
expansão maior): pictogramas para os gestos-chave (posição lateral,
teste do AVC, desengasgamento); agrupar os conselhos condicionais ("se
estiver consciente" / "se não acordar") em mini-fluxos; e reescrever os
conselhos leigos seguros que ainda estão ocultos (o backlog que o
verificador agora dimensiona).

## v0.15.0 — aconselhamento ao utente ("O que pode fazer")

Passa a mostrar-se, no ecrã de resultado, um cartão com conselhos
práticos para o fluxo e a cor apurados. Mudança puramente aditiva: a
lógica de triagem não muda (as prioridades e as cores mantêm-se
exatamente iguais).

- **Nova fonte de dados `app/data/aconselhamento.json`.** A coluna de
  aconselhamento da tabela de Manchester é importada por
  `scripts/importar_aconselhamento.py` e organizada por fluxograma e cor
  (56 fluxos, 935 itens no total). O item é uma lista deduplicada por
  (fluxo, cor), pela ordem de primeira aparição. O ficheiro passa a estar
  documentado no guia dos dados.
- **Dupla gravação `texto` / `texto_utente`, tal como as perguntas.** Cada
  item guarda o `texto` clínico da tabela (fidelidade, e é o que os
  integradores recebem em `/integracao/triagem`) e, quando existe uma
  versão leiga segura, um `texto_utente` em linguagem do dia a dia (ver
  `scripts/_aconselhamento_utente.py`). Neste momento 572 dos 935 itens
  (61%) já têm versão de utente.
- **Política de segurança: o utente só vê conselhos leigos validados.** O
  aconselhamento da tabela está escrito para o profissional de triagem e
  inclui ações que não devem ser dadas como instruções a um leigo (avaliar
  a escala de Cincinnati, isolamento de contacto, ativar meios, fármacos
  por nome, contactar o CIAV, enviar a polícia...). Por isso, ao contrário
  das perguntas, o frontend **não** recua para o texto clínico: só mostra
  itens com `texto_utente`. Os restantes ficam no backend, mas nunca
  aparecem ao utente. Onde o gesto do leigo difere do gesto clínico,
  segue-se a ação segura em casa (por exemplo, perante um membro
  deformado, "não tente endireitar o membro, mantenha-o quieto", em vez de
  "alinhar o membro").
- **O cartão aparece no ecrã de resultado, não só no encaminhamento.** É
  aí que os conselhos de primeira ajuda são mais precisos: numa situação
  vermelha, o utente liga 112 e pode nunca chegar ao ecrã de
  encaminhamento. O bloco "Porquê esta recomendação?" do encaminhamento
  mantém-se como estava.
- **Textos só em português, com recuo seguro para inglês.** A tabela é só
  em português; em inglês, os conselhos por item mostram o texto
  português (como já acontece noutros pontos). O título "O que pode fazer"
  / "What you can do" e a nota de rodapé são bilingues.
- **Continua a aguardar validação clínica.** Como o autocuidado e as
  perguntas do utente, estas reescritas são uma proposta e estão marcadas
  como sujeitas a validação clínica antes de uso real.

## v0.14.3 — tradução completa das avaliações guardadas e dicionário de sinónimos maior

Duas correções pontuais, sem qualquer alteração à lógica clínica de
triagem (as prioridades e as cores mantêm-se).

- **As avaliações guardadas passam a acompanhar a troca de língua.** No
  ecrã de "avaliações anteriores", o nome da queixa (por exemplo
  *Dispneia no adulto* / *Shortness of breath in adults*), a etiqueta da
  cor e as perguntas respondidas ficavam na língua em que tinham sido
  guardadas e não mudavam ao alternar PT/EN. O histórico passa a guardar
  as duas línguas em cada entrada (em vez de um único texto já resolvido)
  e resolve o texto visível segundo a língua ativa no momento de mostrar,
  tal como o resto da aplicação já fazia. As entradas guardadas antes
  desta versão mantêm a língua em que foram registadas.
- **Dicionário da pesquisa em texto livre alargado.** O
  `app/data/sinonimos.json` junta agora os termos anteriores com a lista
  clínica de palavras alargada: cada um dos 56 fluxos de triagem passa a
  ter sinónimos (antes eram 39), preservando a união de todos os termos
  distintos dos dois lados. Isto elimina os avisos de "fluxo sem
  sinónimos" do validador e alarga aquilo que o utente pode escrever
  (incluindo variantes PT/EN/ES/FR/DE/IT). Continua a aguardar revisão da
  equipa clínica, como o cabeçalho do ficheiro indica.

## v0.14.2 — feriados municipais, robustez e afinações do frontend

Um conjunto de pequenas melhorias, todas a validar com o SESARAM. A
lógica clínica de triagem (prioridades e cores) mantém-se; muda o
encaminhamento em alguns casos e vários textos mostrados ao utente.

- **Feriados municipais por concelho.** Cada um dos 11 concelhos passa a
  ter o seu feriado municipal, aplicado **só às unidades desse concelho**
  (Funchal 21 ago, Santa Cruz 15 jan, Machico 8 mai, Santana 25 mai,
  Calheta 24 jun, Ponta do Sol 8 set, Ribeira Brava 29 jun, Câmara de
  Lobos 4 out, São Vicente 22 jan, Porto Moniz 22 jul, Porto Santo 24
  jun). Nesses dias fecham as consultas do concelho, mas — como nos
  feriados nacionais/regionais — as urgências e o atendimento urgente
  (horário 24h) mantêm-se abertos. A decisão usa sempre o `concelho` de
  **cada** unidade em `unidades.json`: por isso o Centro de Saúde do
  Santo da Serra, que tem concelho «Machico», fecha a 8 de maio (feriado
  de Machico) e não a 15 de janeiro (Santa Cruz) — comportamento
  pretendido. Implementado passando o concelho por `horarios.esta_aberto`
  / `proxima_abertura` até `feriados.feriado_em`; ver
  `FERIADOS_MUNICIPAIS` em `app/core/feriados.py`.
- **Vermelho sem «tempo de espera» nem «pessoas em espera».** Num caso
  emergente (vermelho) o doente é atendido de imediato — mostrar tempo de
  espera ou fila seria enganador, e o próprio site do SESARAM não publica
  espera para a cor emergente. A referência do hospital no vermelho deixa
  de trazer esses dois indicadores (a ação continua a ser ligar 112).
- **Azul com alternativas, como o verde.** Numa situação não urgente
  (azul) recomenda-se o centro de saúde principal (o mais próximo / mais
  rápido de chegar) e passa a haver a secção «Alternativas» com os dois
  centros seguintes — antes só aparecia um. No Porto Santo, a regra da
  ilha mantém apenas a unidade local.
- **«SEISRAM» → «SESARAM» nos textos.** Todas as menções em comentários,
  documentação e textos passam a dizer SESARAM. Os **endereços web reais**
  do sistema de tempos de espera (`web.sesaram.pt/SEISRAM_WBE_WEB/…`)
  ficam intactos, porque `SEISRAM_WBE_WEB` é o caminho verdadeiro do
  serviço em produção — mudá-lo partiria a ligação.
- **Pergunta das 24 horas: «xixi» → «urina».** «…dificuldade em controlar
  o xixi ou as fezes?» passa a «…dificuldade em controlar a urina ou as
  fezes?». As perguntas dirigidas a crianças (ex.: «Deixou de fazer
  xixi…») mantêm a palavra do dia a dia.
- **Linguagem simples em destaque nas queixas.** Em várias queixas, o
  termo clínico troca de posição com a explicação em linguagem comum: o
  título a negrito passa a ser o que a pessoa reconhece e o termo técnico
  fica por baixo. T.C.E. → **Pancada ou traumatismo na cabeça**;
  Problemas oftalmológicos → **Problema nos olhos ou na visão**;
  Palpitações → **Sensação de batimentos cardíacos rápidos ou
  irregulares**; Hemorragia gastrointestinal → **Sangue nos vómitos ou
  nas fezes**; Grande traumatismo → **Acidente ou lesão grave**; Erupções
  cutâneas → **Manchas, borbulhas ou erupção na pele**. E «RN que não está
  bem (< 28 dias)» passa a **Recém-nascido que não está bem (< 28 dias)**.
  Os fluxogramas e o documento de validação clínica foram regenerados.
- **Frontend mais limpo.** Saiu do ecrã a nota de metodologia dos tempos
  de viagem («rede simplificada» / «tabela local da aplicação»): não
  acrescentava nada para o utente e o detalhe fica documentado para quem
  analisar a aplicação. Os chips de trajeto (com «estim.» / «registado»)
  mantêm o contexto útil.
- **Dicionário de sinónimos alargado.** A pesquisa em texto livre ganhou
  muitos mais termos do dia a dia (e equivalentes em inglês) por queixa,
  mantendo as mesmas chaves (`app/data/sinonimos.json`).

Como sempre, estes textos e regras são uma proposta e precisam de revisão
por uma equipa clínica antes de qualquer uso real.

## v0.14.1 — perguntas em linguagem para o utente

Uma passagem de legibilidade e de fluxo por cima do modelo de Manchester.
A lógica de triagem (prioridades e cores) não muda; o que muda é como as
perguntas se leem e o que a pessoa vê no ecrã.

- **Perguntas reescritas em linguagem do dia a dia.** Cada discriminador
  passa a ter uma versão para o utente (`texto_utente` / `texto_utente_en`),
  escrita para ser compreendida por alguém com pouca instrução, com a
  antiga descrição clínica integrada dentro da própria pergunta. O jargão
  que ninguém conhece é traduzido para o que a pessoa realmente nota — a
  escala NEWS passa a assentar em sintomas ("Sente-se muito mal ou quase a
  desmaiar?") e os níveis de transporte A/B/C passam a palavras simples
  ("levado de helicóptero com cuidados médicos"). O texto clínico oficial
  (`texto` / `texto_en`) e a `descricao` ficam intactos nas regras, por
  isso os fluxogramas e o documento de validação clínica continuam a
  mostrar as perguntas de Manchester tal e qual — quem revê lê o texto
  oficial em `/fluxogramas` sem ter de procurar uma fonte à parte.
- **Sem cor durante as perguntas.** A barra de prioridade e a cor de
  Manchester saíram do ecrã das perguntas; a cor só aparece no resultado
  final, para não condicionar as respostas. O texto de ajuda à parte
  também desapareceu — o seu conteúdo passou para dentro da pergunta.
- **Saiu a página inicial de "sinais de emergência".** Aqueles sinais
  eram uma lista-exemplo feita à mão e não um conjunto de discriminadores
  P1 transversal a todos os fluxos, por isso a aplicação começa já na
  escolha da queixa; os discriminadores vermelhos (P1) de cada fluxo
  continuam a ser os primeiros a ser perguntados. O endpoint
  `/api/red-flags` mantém-se disponível, mas deixa de ser usado no ecrã.
- **Desfecho "sem discriminador positivo" mais justo.** Responder "não" a
  tudo dava sempre azul (P5). Em fluxos cujo discriminador menos urgente
  já é urgente, isso era um salto clinicamente estranho. O desfecho passa
  a ficar **um nível de prioridade abaixo do discriminador menos urgente
  do fluxo**, sem passar de azul: o *Pedido para terceiros* termina em
  amarelo (P3) em vez de azul, a *autoagressão* e o *grande traumatismo*
  terminam em verde (P4); os outros 53 fluxos (cujo menos urgente é verde)
  continuam a terminar em azul, tal como antes. Os três fluxogramas
  afetados foram regenerados.

Como sempre, as frases para o utente e estes desfechos por defeito são uma
proposta e precisam de revisão por uma equipa clínica antes de uso real.

## v0.14.0 — discriminadores de Manchester (motor baseado em discriminadores)

A maior mudança do modelo clínico até agora. Os oito fluxos-exemplo
feitos à mão foram substituídos pelos **discriminadores reais do Sistema
de Triagem de Manchester**, importados da tabela de referência oficial
(fluxograma, prioridade, discriminador e descrição clínica). O motor de
triagem passou de árvores de decisão arbitrárias para um **modelo
baseado em discriminadores**, muito mais próximo do funcionamento real
de Manchester.

- **Motor baseado em discriminadores.** Cada queixa é agora uma lista
  de discriminadores ordenados por prioridade clínica (P1–P5). O motor
  faz uma pergunta de sim/não por discriminador, da prioridade mais
  alta para a mais baixa: o **primeiro "sim" decide a cor** e termina a
  triagem; se todas as respostas forem "não", o desfecho é **azul** (o
  "sem discriminador positivo" da tabela). Isto substitui a árvore
  `sim`/`nao` → `proxima`. A prioridade mapeia para a cor de forma
  canónica: P1 vermelho, P2 laranja, P3 amarelo, P4 verde, P5 azul.
- **56 fluxogramas, 1187 discriminadores.** Face a 7 queixas-exemplo.
  Fluxos de adulto e pediátricos, marcados com um campo `pediatrico`.
  Cada discriminador guarda o seu id numérico oficial (`disc_id`) para
  futuras auditorias e cruzamento de dados.
- **Descrições clínicas mostradas aos utentes.** A coluna de descrição
  da tabela (a explicação clínica de cada discriminador) é importada
  para o campo `descricao` de cada discriminador e mostrada como ajuda
  da pergunta, para o utente perceber o que está a ser perguntado.
- **Importação reproduzível.** Novo `scripts/importar_manchester.py`
  regenera `app/data/rules/*.json` a partir da tabela-fonte (guardada
  em `docs/manchester/`), com um dicionário PT→EN curado para os 186
  textos únicos de discriminador e os 56 nomes de fluxo. Reexecutável.
- **Indicador de prioridade na interface.** Os antigos três pontos de
  fase foram substituídos por uma barra de prioridade de Manchester com
  cinco segmentos que mostra, na cor correspondente, em que nível de
  prioridade vai a avaliação.
- **Validação mais simples e mais estrita.** O validador de arranque
  deixou de verificar ciclos/perguntas inalcançáveis (impossíveis numa
  lista plana); passa a verificar que cada discriminador tem uma
  prioridade válida, uma cor que corresponde a essa prioridade, texto
  não vazio, e que os discriminadores estão ordenados de P1 para P5. O
  novo desenho Mermaid mostra a sequência linear de discriminadores. As
  regras continuam em JSON editável, fora do código.
- **Ainda por validar clinicamente.** Os discriminadores vêm tal e qual
  da tabela de referência e ainda exigem validação clínica antes de uso
  real — o documento de validação (`scripts/gerar_validacao_clinica.py`)
  foi atualizado para o novo modelo precisamente para essa revisão. As
  descrições dos discriminadores estão só em português para já (a
  interface continua totalmente bilingue e recua para o português nesse
  texto clínico).

## v0.13.1 — explicabilidade, logging e consolidação

Uma versão de consolidação, guiada por uma revisão de código externa:
sem funcionalidades clínicas novas, mas o protótipo passou a
explicar-se — aos utentes, aos clínicos e a quem lê o repositório.

- **Explicabilidade ("Porquê esta recomendação?").** Todas as respostas
  de `/api/encaminhamento` passam a trazer `motivos`: a lista ordenada
  e bilingue dos fatores por trás da decisão — a cor estimada, a
  política aplicada (e a sua fonte: configuração, desfecho do
  fluxograma ou recuo seguro), se a unidade está aberta, o tempo de
  viagem estimado, o tempo de espera atual, a regra experimental de
  troca quando atuou, e a regra da ilha no Porto Santo. A interface
  mostra a lista num bloco expansível no cartão da recomendação, para
  um clínico poder auditar a decisão sem ler código. Módulo novo
  `app/core/motivos.py`; a lógica de decisão em si não mudou.
- **Divisão do `routing.py` (responsabilidade única).** As frases
  mostradas ao utente (horários em inglês, "abre segunda-feira às
  08:00", textos de chegada, contexto do dia) mudaram-se para
  `app/core/routing_textos.py`; o routing passou a só decidir, o
  routing_textos escreve, o motivos explica. Os nomes antigos
  continuam importáveis a partir de `routing`
  (`docs/adr/0010-divisao-routing.md`).
- **Logging na aplicação.** A app passou a usar o módulo `logging`
  padrão: uma linha INFO no arranque (versão, fluxos e perguntas
  validados), WARNINGs quando uma fonte de tempos de espera falha ou
  se servem dados desatualizados, quando o OSRM recua para a rede
  calibrada, e quando o hospital de referência configurado não tem
  urgência aberta nos dados (o recuo seguro da v0.12.1). Nível
  ajustável com `ONDE_IR_LOG`. Os logs nunca contêm dados do utente —
  sem coordenadas, sem respostas (`docs/adr/0011-logging.md`). Os
  scripts de linha de comandos mantêm o `print()` de propósito: o
  output é a interface deles.
- **Documentação reorganizada (este ficheiro faz parte disso).** O
  histórico de versões saiu dos READMEs e vive aqui; os guias de
  edição de dados mudaram-se para `docs/GUIA_DOS_DADOS.md` (EN:
  `docs/DATA_GUIDE.md`); as decisões de desenho existem agora também
  como ADRs de uma página em `docs/adr/`; o estado da validação tem a
  sua própria checklist em `docs/VALIDACAO.md` (EN:
  `docs/VALIDATION.md`); e os números de latência medidos vivem em
  `docs/PERFORMANCE.md`, produzidos pelo novo
  `scripts/benchmark_desempenho.py`. Os READMEs passaram a ser uma
  porta de entrada curta (o que é, como correr, como funciona, onde
  está tudo) — cerca de um quarto do tamanho anterior.
- **Integração contínua.** Um workflow de GitHub Actions
  (`.github/workflows/ci.yml`) corre a validação de dados, a auditoria
  de traduções e a bateria de testes com cobertura em cada push e
  pull request.
- **Testes: 282 (eram 261), todos a passar** — os novos fixam a
  explicabilidade de todos os ramos, o aviso no log do recuo do
  hospital (e que não deixa escapar a localização do utente), o
  benchmark, e a forma da documentação reorganizada, para nada disto
  apodrecer em silêncio.

## v0.13.0 — uma versão de engenharia — Docker, documentação de arquitetura e cobertura medida

Nesta versão não mudou nenhuma lógica clínica (regras, política de
encaminhamento, dados das unidades e traduções estão exatamente como na
v0.12.1, e os 261 testes continuam todos a passar). A versão inteira é
sobre tornar o projeto mais fácil de correr, avaliar e entregar:

- **Docker.** Um `Dockerfile` (Python 3.12 slim, utilizador não-root,
  health check no `/api/saude`) e um `docker-compose.yml` de um serviço
  só. Qualquer pessoa passa a arrancar o protótipo com
  `docker compose up --build`, sem instalar Python — útil para
  demonstrações e para quem pegar no projeto a seguir. Correr
  nativamente continua a funcionar exatamente como antes.
- **Documentação de arquitetura.** [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md)
  (e [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) em inglês) explica o
  *porquê* do desenho: regras como dados, validação no arranque, o
  stateless e a ausência deliberada de base de dados, o modelo de viagem
  em camadas, as redes de segurança do scraping, os modos de degradação,
  e os critérios que justificariam mudar cada decisão. O README fica como
  o *como usar*; o documento de arquitetura é o *como pensar sobre ele*.
- **Cobertura de testes medida.** O `pytest-cov` entra nos requisitos e o
  `scripts/cobertura_testes.py` mede a cobertura (atualmente **91%**
  sobre `app/`, com 261 testes), gera opcionalmente um relatório HTML
  navegável, e — com `--atualizar-readme` — reescreve os badges no topo
  dos dois READMEs, para que nunca fiquem desatualizados em silêncio.
- **Uma porta de entrada mais informativa.** Os badges e o *O projeto em
  números* no topo dos dois READMEs dão de relance a dimensão real do
  protótipo (fluxos, perguntas, unidades, freguesias, tempos medidos,
  endpoints), com cada número a vir dos próprios ficheiros de dados.

## v0.12.1 — vermelho, laranja e amarelo diretos ao hospital

A mudança veio da reunião de acompanhamento: a indicação do SESARAM é que
todos os vermelhos e laranjas, e (por agora) todos os amarelos, sejam
encaminhados diretamente para o Hospital Dr. Nélio Mendonça — e não para
o ponto de urgência aberto mais próximo. Até esta versão, essas cores
consideravam qualquer urgência aberta (hospitalar ou o atendimento
urgente 24 h dos centros de saúde).

- **Uma política de destino, guardada em dados.** A regra vive em
  `app/data/encaminhamento.json` (`hospital_id` mais a lista de cores em
  `direto_para_hospital`), editável pela equipa clínica como tudo o
  resto — sem tocar em código. Retirar uma cor da lista repõe, para essa
  cor, o comportamento por proximidade (urgência aberta mais próxima,
  ordenada por tempo de estrada). Cada resposta de encaminhamento passa
  a trazer um bloco `politica` (`destino`, `fonte`, `aplicada`) para as
  interfaces e integrações poderem explicar a decisão.
- **O vermelho mantém o 112 primeiro.** A ação no vermelho continua a
  ser "ligar 112"; o que muda é a unidade mostrada por baixo, que passa
  a ser o hospital de referência (é para lá que a emergência transporta)
  em vez da urgência mais próxima.
- **A válvula para "certos amarelos", pronta a usar.** Um desfecho
  amarelo em `app/data/rules/*.json` pode declarar `"destino":
  "atendimento_urgente"`, e esse desfecho específico volta ao ponto de
  atendimento urgente aberto mais próximo (com a ordenação por tempo de
  estrada da v0.11 e a regra experimental de troca por espera). O
  validador do arranque só aceita o campo em desfechos amarelos e só com
  valores válidos, portanto um erro de escrita não muda o encaminhamento
  em silêncio; os fluxogramas desenhados (documento de validação e
  pré-visualização `/fluxogramas`) marcam estes desfechos com "(pode ir
  ao atendimento urgente)". Nenhuma regra em produção o usa ainda — está
  lá para quando a equipa clínica disser quais os amarelos que
  qualificam.
- **Regra da ilha intocada.** No Porto Santo nada atravessa o mar: todas
  as cores continuam a apontar para a unidade local, com a nota de
  transferência nas mais graves.
- **Recuo seguro.** Se o id do hospital configurado não existir nos
  dados ou não tiver urgência aberta (um erro de dados), a app recua
  para a urgência aberta mais próxima em vez de mandar alguém para uma
  porta fechada, e assinala-o (`politica.recuo`).

27 testes novos cobrem a política a partir de vários concelhos, o bloco
`politica`, a espera da cor no hospital, o Porto Santo, a exceção
amarela (incluindo o caso do tempo de estrada do Curral das Freiras), a
validação do arranque, a viagem completa na API (`destino` aceite pelo
`/api/encaminhamento` e propagado pelo `/api/integracao/triagem`), a
marca nos fluxogramas, e estes links do README. Total: 261.

## v0.12 — fluxogramas offline em todo o lado, e pré-visualização viva

O ponto de partida foi uma regressão: os fluxogramas tinham deixado de
aparecer no `docs/validacao_clinica.html`. A causa era a biblioteca de
desenho ser ida buscar a um CDN público (`unpkg.com`) no momento de
abrir, atrás de um `if (window.mermaid)` silencioso — quando o CDN
estava lento ou em baixo (esteve, repetidamente, ao longo de 2025–2026),
a biblioteca não carregava e as árvores simplesmente desapareciam, sem
um erro que explicasse porquê. Esta versão remove essa dependência, torna
qualquer falha visível, e acrescenta uma forma de ver as árvores a
atualizarem-se enquanto se editam as regras.

- **Documento de validação autossuficiente.** A biblioteca Mermaid
  (MIT) passa a estar **embutida no HTML gerado**
  (`static/vendor/mermaid.min.js`, vendorizada). O
  `docs/validacao_clinica.html` desenha os fluxogramas offline e pode ser
  enviado por email como um único ficheiro — sem rede, sem CDN. Se um
  diagrama não puder ser desenhado (por exemplo, quando uma edição às
  regras introduz um erro), o documento passa a imprimir o erro no lugar,
  com a fonte Mermaid logo abaixo, em vez de o esconder.
- **Pré-visualização viva em `/fluxogramas`** (com o servidor a correr,
  abrir http://127.0.0.1:8000/fluxogramas). Uma página interna nova
  (não ligada à interface do utente — é uma ferramenta para quem edita e
  valida regras) mostra cada fluxograma desenhado a partir das regras
  atuais em `app/data/rules/*.json`. Edita-se uma regra, guarda-se, e a
  árvore redesenha: o `GET /api/fluxogramas` **relê e revalida as regras
  do disco a cada pedido**, por isso não é preciso reiniciar o servidor.
  Atualiza-se sozinha a cada 5 s (com interruptor), tem um seletor PT/EN,
  um botão "copiar código Mermaid" por árvore (para colar em mermaid.live
  e editar visualmente), e se um ficheiro de regras estiver inválido
  mostra a mensagem de validação tal e qual, mantendo no ecrã as últimas
  árvores válidas.
- **Fluxogramas bilingues.** As árvores passam a desenhar-se também em
  inglês, a partir dos campos `*_en` já existentes nas regras, com um
  recuo deliberado para português onde falte tradução (uma árvore meio
  traduzida é útil e denuncia a falha; uma árvore cheia de buracos não
  é). As caixas de desfecho usam o nome inglês da cor (RED, ORANGE…); as
  classes de estilo internas ficam em português.
- **Também sem CDN na app.** O Leaflet (o mapa) e o gerador de QR
  carregavam igualmente do `unpkg.com`; ambos passam a estar
  vendorizados em `static/vendor/` e servidos localmente. Em execução, a
  app não faz qualquer pedido de scripts a terceiros. Os únicos recursos
  externos que restam são os tiles do mapa (CARTO) e as Google Fonts,
  ambos com degradação graciosa se faltarem — a app continua utilizável
  offline, apenas com tipos de letra do sistema e sem mapa de fundo.
- **Como atualizar as bibliotecas vendorizadas.** São ficheiros simples
  em `static/vendor/`; para subir de versão, substitui-se o ficheiro (por
  exemplo `npm pack mermaid@<versão>` e copiar `dist/mermaid.min.js`),
  mantém-se o `LICENSE` correspondente, e atualiza-se `VERSAO_MERMAID` em
  `scripts/gerar_validacao_clinica.py` (há um teste que confirma que os
  dois coincidem).

19 testes novos cobrem as bibliotecas vendorizadas (bundle
autossuficiente, sem CDN no `index.html`), o documento a embutir a
biblioteca e um bloco desenhável por fluxograma, os ficheiros `.mmd` em
disco a corresponderem às regras atuais, a tradução inglesa e o seu recuo
para português, e a API da pré-visualização viva (todos os fluxos, EN,
idioma inválido 422, releitura do disco a cada pedido, erro de validação
legível) e a página. Total: 234.

## v0.11.3 — tempos por estrada numa tabela local e chips de espera

O caso motivador vem da v0.11.2: da Achada da Rocha (Gaula), o modelo
local ordenava mal a Camacha e Gaula. Esta versão ataca-o com um
paliativo assumido e amovível, e aproveita para arrumar o cartão de
resultados.

- **Uma tabela local de tempos por estrada (módulo amovível).**
  `app/data/tempos_medidos.json` guarda, por sítio e por freguesia, o
  tempo e a distância de carro até às unidades relevantes (o hospital e
  os centros de saúde mais próximos). Quando o utente está a menos de
  `raio_ancoragem_km` (3 km) de uma zona registada, sem barreira de
  relevo pelo meio, a app usa esse valor, ajustado pelo desvio até à
  âncora; caso contrário recua para a rede calibrada. A prioridade é:
  OSRM ao vivo (se configurado) > tabela > rede.
- **Dois caminhos para preencher a tabela, que podem coexistir.** O
  recomendado é automático: `python scripts/calcular_tempos_medidos.py
  --motor ors --chave A_TUA_CHAVE` pede as rotas em lotes a um motor de
  rotas (OpenRouteService, com chave gratuita, ou um servidor OSRM
  próprio com `--motor osrm`) e preenche os 598 pares em cerca de um
  minuto, marcando `fonte` e `calculado_em` em cada par. Grava depois de
  cada lote: interromper e retomar é seguro, e o que já está preenchido
  não volta a ser pedido. O caminho manual continua:
  `python scripts/tempos_medidos_relatorio.py --links` gera os links do
  Google Maps prontos a abrir, úteis para conferir ou corrigir pares
  suspeitos, e `--divergencias` lista onde a tabela e a rede mais
  discordam. `python scripts/atualizar_tempos_medidos.py` refaz o
  esqueleto depois de editar as localidades, sem perder o que está
  preenchido; com `--todos`, os destinos passam a ser todas as unidades
  da ilha (mais pares, pensado para o preenchimento automático).
- **Como remover o paliativo:** apagar `app/data/tempos_medidos.json`
  (ou definir `VIAGEM_TEMPOS_MEDIDOS=0`) e a app volta sozinha à rede
  calibrada; pode apagar-se também `app/core/tempos_medidos.py` e os
  três scripts, que nada mais depende deles. Em produção, o caminho
  certo continua a ser um serviço de rotas (ver `docs/INTEGRACAO.md`).
- **Honestidade sobre a qualidade.** O OpenRouteService e o OSRM usam o
  OpenStreetMap com perfis de velocidade genéricos, sem trânsito: na
  Madeira dão tempos muito melhores do que o modelo local, mas abaixo do
  Google Maps. Por isso a nota de transparência no ecrã muda quando o
  método é "medido", cada par guarda a `fonte`, e o
  `GET /api/viagem?unidade=<id>` expõe o método para inspeção.
- **Chips de espera no cartão.** A frase "Espera para a sua cor: ~35
  min · 12 pessoas em espera" deu lugar a dois chips âmbar (relógio e
  pessoas) na linha dos chips de distância e tempo; quando a espera é da
  cor do utente, o chip leva a nota "na sua cor".
- **Distância por estrada no chip.** Quando a tabela responde, o chip da
  distância mostra os quilómetros por estrada (nota "por estrada") em
  vez da linha reta, e o chip do tempo troca "estim." por "registado".
- **Alternativas com mini chips.** Cada alternativa mostra o concelho e
  uma fila de mini pastilhas (distância, tempo de carro, aberto ou
  fechado, espera), mais legível do que a frase corrida e um degrau
  visual abaixo do cartão principal; a reabertura fica numa linha
  discreta.
- **"Alterar localização" virou um mini botão** tipo pílula, mais óbvio
  como ação do que a antiga ligação sublinhada.

33 testes novos guardam o ficheiro de dados e o gerador do esqueleto, a
procura com âncoras (raio, desvio, barreiras, interruptores para
desligar), a prioridade OSRM > tabela > rede, o encaminhamento e o
`/api/viagem`, e o script de cálculo com o motor simulado (os testes não
fazem pedidos à rede). Total: 215.

## v0.11.2 — textos mais limpos e chips de distância e tempo

Uma versão de acabamento. A lógica de encaminhamento não mudou; os 170
testes anteriores continuam a passar e 12 novos guardam as alterações
abaixo.

- **Sem travessões em nada que o utente veja.** Todos os travessões dos
  textos da interface foram reescritos com vírgulas, dois pontos ou
  pontos finais: `textos.js`, os conselhos de autocuidado
  (`autocuidado.json`), as mensagens de troca do `routing.py`, a nota de
  tempos de viagem do backend (`viagem.py`) e os títulos do PDF clínico.
  Um teste de regressão varre o `textos.js`, os ficheiros de dados e uma
  resposta real do `/api/encaminhamento` (PT e EN) e rebenta se algum
  travessão voltar a entrar.
- **Rótulos do modo manual simplificados.** "Freguesia (se souber)"
  passou a "Freguesia" (e "Sítio ou zona"); a primeira opção de cada
  lista já é "Não sei", por isso o parêntesis era redundante. A
  introdução do ecrã "Onde está?" foi reescrita no mesmo espírito.
- **Horários lidos como prosa.** Os *textos* de horário das unidades
  passaram de "08:00-20:00" para "das 08:00 às 20:00" (os campos máquina
  `horas` ficaram intactos). O tradutor `_horario_en` aprendeu a nova
  redação ("Weekdays, 08:00 to 20:00").
- **Distância e tempo de carro viraram chips.** No cartão de cada
  unidade saíram da linha corrida ("Centro de saúde, Santa Cruz, a
  1.7 km · ~7 min…") e são agora duas pastilhas distintas por baixo do
  cabeçalho, com pequenos ícones (pin e carro) e um tom azul claro que
  segue a linguagem do selo aberto/fechado. Sem estimativa por estrada,
  o chip da distância leva a nota "linha reta".
- **Caminhos de produção para tempos reais documentados.** O modelo
  local do protótipo pode ordenar mal duas unidades próximas (da Achada
  da Rocha prefere por pouco a Camacha em vez de Gaula; quem lá conduz
  sabe que é ao contrário). O `docs/INTEGRACAO.md` passa a descrever as
  três vias para resolver isto a sério: OSRM alojado internamente para
  piloto (já suportado via `VIAGEM_OSRM_URL`), uma **API paga de rotas
  (Google Routes API ou equivalente) como opção recomendada para
  produção**, com a avaliação RGPD/EPD obrigatória, e uma tabela de
  tempos por estrada como paliativo (implementada na v0.11.3).

## v0.11.1 — localização manual mais fina (freguesia e sítio)

**Porquê.** Quando a localização automática falha ou está errada, a app
deixava escolher apenas o **concelho** — e emprestava as coordenadas da
primeira unidade de saúde desse concelho. É grosseiro de mais: quem está
na Camacha ou no Caniço e escolhe "Santa Cruz" fica com o centro da vila,
do lado errado do concelho. Com o modelo de estrada da v0.11 isto passou
a ter um custo visível: da Camacha, o palpite pela vila encaminha para o
centro de saúde de Santa Cruz (**~19 min**) quando o da Camacha está a
**~8 min**.

**Como.** Um novo ficheiro de dados editável, `app/data/localidades.json`,
guarda a RAM como uma árvore **concelho → freguesia → sítio** (11
concelhos, 53 freguesias, 145 sítios), com coordenadas recolhidas e
verificadas pelo estagiário; os centros de concelho são as vilas,
coerentes com `rede_viagem.json`. O ecrã "Onde está?" (`GET
/api/localidades`) mostra três caixas nativas em cascata: escolhe-se o
concelho, se quiser a freguesia, se quiser o sítio — nomes que qualquer
pessoa conhece de cor, sem mapa para apertar, sem GPS. Escolher só o
concelho continua a funcionar exatamente como antes ("Não sei" nos outros
dois), por isso nada se perde. Como nos fluxogramas e na rede de estradas,
é **dado, não código**: `app/core/localidades.py` valida no arranque (ids
únicos, cada ponto dentro da caixa da ilha certa e coerente com a rede de
viagem, cada freguesia com forma de ser situada) e emite **avisos brandos**
para olhos humanos — um sítio a mais de 12 km do centro do concelho,
quase-duplicados, ou entradas por confirmar. O `python
scripts/validar_dados.py` corre as mesmas verificações. Cada nível expõe
um `centro` calculado (uma freguesia sem coordenada própria usa o
centroide dos seus sítios); o seletor resolve para o nível mais específico
escolhido e mantém tudo no dispositivo.

**Notas sobre a qualidade dos dados (para validação da equipa).** Algumas
freguesias surgem atualmente sem sítios associados, uma vez que não foi
possível obter informação completa e fiável através das fontes públicas
disponíveis. Não existe uma fonte oficial única que reúna todos os sítios
de todas as freguesias da Região Autónoma da Madeira, pelo que a informação
foi compilada a partir dos websites de várias Juntas de Freguesia e de
outras fontes de referência. Como consequência, é possível que alguns
sítios ainda não estejam contemplados, embora todos os concelhos e
freguesias da Região Autónoma da Madeira se encontrem representados. Antes
de uma eventual implementação pelo SESARAM, recomenda-se a validação e o
complemento desta informação, de forma a garantir que todos os sítios se
encontram corretamente identificados. Esta funcionalidade é particularmente
útil para utilizadores que não autorizem o acesso à localização, uma vez
que os residentes conseguem frequentemente indicar o local onde se
encontram através dos nomes dos sítios. Para turistas ou residentes
recentes que possam não conhecer essas designações, a aplicação
disponibiliza a opção **"Não sei"** tanto na seleção da freguesia como na
seleção do sítio.

## v0.11 — tempos de viagem numa rede calibrada de estradas

**Porquê.** Até à v0.10, "mais próxima" era distância em linha reta, e a
regra experimental de troca somava uma espera real (recolhida do
SESARAM) a uma viagem adivinhada (linha reta ÷ 50 km/h) — uma medição
com um palpite. Na Madeira, a linha reta engana mesmo: o Curral das
Freiras tem o Funchal "ao lado" no mapa com uma serra pelo meio, e a
estrada para Câmara de Lobos passa à porta do hospital. A v0.11
substitui o palpite por uma estimativa por estrada — **sem enviar a
localização de ninguém para fora do servidor e sem chamadas de rede em
funcionamento**.

**Como (três camadas, em `app/core/viagem.py`).**
A camada por omissão é uma **rede calibrada de estradas**
(`app/data/rede_viagem.json`): ~16 pontos de referência ligados pelos
troços reais (VR1, VE3, VE4, ER101, …) com minutos típicos, mais
**barreiras** de relevo (a crista do Curral, o Pico Grande) que os
acessos curtos em linha reta não podem atravessar. O tempo entre dois
pontos quaisquer é o caminho mais curto nesse grafo (Dijkstra), com os
acessos locais estimados por um modelo simples de fator de desvio. Tal
como os fluxogramas clínicos, é **dado editável, não código** — quem
conhece a ilha corrige os minutos de uma ligação; a validação no
arranque apanha erros de estrutura (também corre em
`python scripts/validar_dados.py`). Opcionalmente, definir a variável de
ambiente `VIAGEM_OSRM_URL` para um servidor **OSRM alojado pela
instituição** liga o cálculo de rotas verdadeiro (um pedido `/table`
para todas as unidades), com tempo limite curto, cache, arrefecimento
após falha e recuo automático para a rede. Está **desligado por
omissão**: usar o servidor público de demonstração enviaria coordenadas
de utentes para terceiros (RGPD) — decisão que pertence à instituição,
discutida em `docs/INTEGRACAO.md`.

**O que mudou no comportamento.**
As candidatas passam a ser ordenadas por **tempo de viagem estimado**
(distância como desempate), as mensagens dizem "8.9 km, ~29 min de
carro", os cartões e as alternativas mostram os minutos, e a regra de
troca compara *espera real + viagem por estrada*. As ilhas nunca se
misturam: entre a Madeira e o Porto Santo a estimativa é `None`. A
resposta traz um bloco `viagem_info` e cada unidade um `tempo_viagem`
(`{"minutos", "metodo": "rede"|"medido"|"osrm"}`; no método "medido"
também `distancia_km`, por estrada), e `GET /api/viagem` expõe o
estimador para inspeção.

**Avaliação honesta.** `python scripts/avaliar_viagem.py` compara os
dois métodos com 16 percursos de referência
(`app/data/percursos_referencia.json`, tempos típicos, por confirmar):
o erro absoluto médio cai de **10,4 min (linha reta) para 1,9 min**, o
pior caso de **24 para 5 min**. Editar os minutos da rede e voltar a
correr o guião é o ciclo de calibração.

## v0.10 — dados confirmados, histórico no dispositivo e inglês completo

- **Coordenadas de unidades confirmadas.** Várias coordenadas de centros de
  saúde foram confirmadas e marcadas com `dados_confirmados: true`; as
  restantes continuam a `false`. (v0.10)
- **Histórico no dispositivo.** As avaliações passadas ficam guardadas
  **apenas no navegador** (localStorage) — nunca são enviadas para o
  servidor — para o utente poder rever o que respondeu e quando, e apagar
  quando quiser. Mantém a promessa de "não guardamos nada" do lado do
  servidor. (v0.10)
- **Crachá de versão que se corrige sozinho.** A versão mostrada no topo é
  lida do backend (`/api/saude`) no arranque, por isso deixa de poder ficar
  desatualizada. (v0.10.1)
- **PDF abre numa aba visível.** O botão do PDF ("Abrir PDF") abre o
  documento numa nova aba, com descarregamento como alternativa, para o
  resultado ser visível em vez de um descarregamento silencioso. (v0.10.1)
- **PDF de uma página.** O PDF de orientação foi reduzido ao essencial
  (prioridade, recomendação, unidade, sinais de alarme, contactos) e cabe
  agora sempre numa página; a distância em linha reta foi retirada dele.
  (v0.10.2)
- **Auditoria de traduções.** `python scripts/auditar_traducoes.py` aponta
  qualquer texto de interface ou clínico sem versão inglesa — deteção, não
  tradução automática (o conteúdo clínico deve ser traduzido por uma
  pessoa). (v0.10.2)
- **Inglês completo.** Os seis fluxogramas clínicos que faltavam foram
  traduzidos, e os textos gerados pelo backend (mensagem de encaminhamento,
  nome do dia, horários das unidades) passaram a ter versão inglesa, por
  isso o modo inglês deixa de mostrar português. (v0.10.3)

## v0.9 — exportação em PDF e endpoint de integração

**Botão "Descarregar PDF".** No ecrã de resultado, o utente pode descarregar
um resumo de orientação em PDF (cor de prioridade, queixa, respostas dadas,
unidade sugerida com morada/telefone/horário, alternativas, autocuidado e
contactos). O documento é gerado no servidor com `reportlab` (Python puro,
instala-se com `pip` em qualquer sistema, incluindo Windows). Traz um espaço
de identificação de **preenchimento manual** e o mesmo aviso da app: é
orientação, não substitui avaliação clínica. O botão antigo de imprimir
continua lá.

**Preparação para integração.** Três endpoints novos, pensados para consumo
externo (ver `docs/INTEGRACAO.md`):
`POST /api/integracao/triagem` (triagem + encaminhamento numa só chamada),
`POST /api/exportar_pdf` (PDF para download) e
`POST /api/exportar_pdf_base64` (o mesmo PDF em base64, para anexar).
`docs/INTEGRACAO.md` descreve, de forma neutra, o que já está pronto, o
potencial da integração e as questões a apurar com a equipa de informática
do SESARAM sobre a plataforma interna de destino.

## v0.8 — tempos de espera em tempo real

**De onde vêm.** O SESARAM publica, no sistema SESARAM, duas páginas
públicas com os tempos de espera — a do Hospital Dr. Nélio Mendonça
(por área clínica e pelas cinco classificações de Manchester) e a dos
centros de saúde com atendimento urgente. A app lê essas duas páginas
(`app/core/espera.py`), reconhece os dois formatos ("8m", "2h37",
"1h05 / 3", tabelas por cor) e associa cada linha às unidades do
projeto por `app/data/espera_nomes.json`.

**O que aparece na app.** Na unidade recomendada e nas alternativas
abertas surge o tempo estimado; no hospital é a espera **da cor do
utente** (um laranja vê a espera dos "Muito Urgentes", não a média
geral). Por cima aparece "Tempos de espera do SESARAM, atualizados às
HH:MM". Quando não há dados — sem internet, site em baixo, ou fora das
unidades cobertas — a app di-lo e decide como antes, só por distância e
horários. Endpoint: `GET /api/espera` (com `?atualizar=true` força uma
descarga fresca, respeitando o intervalo mínimo).

**Regra experimental de encaminhamento (por validar).** Para laranja e
amarelo, a app pode sugerir uma unidade um pouco mais longe se isso
poupar tempo total (viagem estimada + espera atual). As salvaguardas
são propositadamente conservadoras e estão no topo de `espera.py` para
serem afinadas com a equipa clínica: só troca se poupar **≥ 30 minutos**
e o desvio for **≤ 15 km**; nunca troca sem dados dos dois lados; e
**nunca** se aplica ao vermelho. Quando troca, explica porquê na
mensagem. Isto — como as regras de triagem — está marcado como **por
validar** e entra no documento de validação clínica.

**Ética e robustez.** Há cache com tempo de vida curto (nunca se
sobrecarrega o site: no máximo um pedido por intervalo, com
identificação honesta no User-Agent), cache negativa (não se insiste
num site em baixo) e reutilização dos últimos dados válidos quando a
descarga falha. A "NOTA" de cortesia do site — que aparece **mesmo com
dados** — nunca é confundida com indisponibilidade. **A prazo, o
caminho robusto é uma API oficial do SESARAM**: se a instituição a
disponibilizar, trocar o leitor de páginas por esse acesso é simples e
recomendado.

**Instalação — atenção.** Esta versão usa duas bibliotecas novas
(`requests` e `beautifulsoup4`). Depois de extrair o zip, corre uma vez
`python -m pip install -r requirements.txt` antes de arrancar o
servidor.

**Scripts úteis.** `python scripts/testar_espera.py` (na tua máquina,
com internet) contacta o SESARAM e mostra o que leu e o que ainda falta
mapear; `python scripts/simular_espera.py` grava um cenário de
demonstração para veres a regra de troca a funcionar sem depender do
site (ideal para a apresentação).

## v0.7 — fluxogramas clínicos e QR de navegação

**Fluxogramas automáticos no documento de validação.** O protocolo de
Manchester é publicado como fluxogramas — e agora o documento de
validação clínica fala essa língua: cada queixa inclui a árvore
desenhada, gerada de `app/data/rules/*.json` por
`app/core/fluxogramas.py`, com os desfechos pintados nas cinco cores e
as perguntas numeradas como na lista. Saltos entre perguntas, caminhos
sem saída ou cores mal atribuídas tornam-se visíveis num relance. O
desenho acontece no navegador com a biblioteca Mermaid **embutida no
próprio documento**, por isso desenha offline e pode ser enviado por
email como um único ficheiro (isto era originalmente carregado de um
CDN, que se revelou instável e fazia os fluxogramas desaparecerem em
silêncio — ver *Novidades da v0.12*); mesmo sem desenho, as perguntas
numeradas
continuam lá. As fontes de cada diagrama ficam em
`docs/fluxogramas/*.mmd` e podem abrir-se e editar-se visualmente em
https://mermaid.live.

**QR de navegação no resultado.** O cartão da unidade recomendada
mostra um código QR com as direções do Google Maps: aponta-se a câmara
do telemóvel e a navegação abre — útil quando a avaliação é feita num
computador, e sai também na impressão. O código é gerado localmente
(biblioteca `qrcode-generator`, MIT), sem enviar nada para lado nenhum;
se a biblioteca não carregar, o bloco simplesmente não aparece.

## v0.6 — tradução, pesquisa e cartões de cuidado

**Botão PT/EN.** No canto superior direito troca-se a língua do interface
a qualquer momento, sem perder as respostas dadas (a escolha fica
guardada no navegador; também funciona abrir com `?lang=en`). Os
conteúdos clínicos traduzem-se ficheiro a ficheiro com campos opcionais
`*_en` ao lado dos portugueses — o fluxo **Febre**
(`app/data/rules/febre.json`) está completo e serve de modelo; nos
restantes fluxos, a app mostra o português até os campos serem
acrescentados. As mensagens longas do encaminhamento continuam em
português por agora. Os textos do interface (botões, títulos) vivem
todos em `static/js/textos.js`.

**Pesquisa da queixa em texto livre.** No ecrã da queixa há agora uma
caixa "escreva o que sente" — por exemplo "dói-me a barriga" sugere Dor
abdominal. Sem inteligência artificial: usa o nome dos fluxos e o
dicionário editável `app/data/sinonimos.json` (acentos e maiúsculas são
ignorados; aceita termos em português e inglês). O
`scripts/validar_dados.py` confirma que cada sinónimo aponta para um
fluxo que existe. Endpoint: `GET /api/queixas/sugerir?q=…`.

**Cartões de cuidado (estrutura do NHS, cores nossas).** O bloco de
autocuidado do verde e do azul passou a dois cartões com faixa de
cabeçalho — "o que fazer" (lista com vistos ✓), "o que evitar" (cruzes
✕) e "Procure ajuda se:" — inspirados nos care cards do serviço de
saúde inglês, mantendo as cinco cores de Manchester intocadas. Os
textos vivem em `app/data/autocuidado.json`, são verificados pelo
validador e entram no documento de validação clínica.

## v0.5 — interface: direção "Serviço público"

O visual segue a linguagem dos portais institucionais portugueses: banda
azul no topo e no rodapé, superfícies brancas com contornos (sem sombras),
etiquetas em maiúsculas pequenas e uma única família tipográfica (Public
Sans). O resultado é apresentado como uma **guia de encaminhamento** — um
cartão com lombada na cor da triagem, pensado também para impressão — e o
mapa usa tiles claros (CARTO sobre dados OpenStreetMap) com o marcador da
unidade recomendada nessa mesma cor. Enquanto os dados carregam, aparecem
esqueletos animados em vez de "A carregar…" (desligam-se automaticamente
para quem pediu movimento reduzido no sistema).

Os azuis são provisórios de propósito: quando houver cores oficiais do
SESARAM, basta trocar `--primaria` e `--primaria-escura` no início de
`static/css/style.css`.
