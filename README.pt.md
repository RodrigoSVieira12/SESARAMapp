# Onde ir? Orientação de utentes na RAM (protótipo — SESARAM)

Este repositório é um protótipo funcional para uma aplicação, do lado hospitalar, que orienta os utentes para o ponto de atendimento certo na Região Autónoma da Madeira: faz triagem de sintomas por perguntas simples de sim/não, estima uma cor de prioridade inspirada em Manchester, e recomenda a unidade adequada mais próxima tendo em conta a hora e os horários. Os textos para o utente e os comentários do código estão em português, porque os utentes e o serviço de saúde são portugueses; ainda assim, a arquitetura, as regras clínicas guiadas por dados e a lógica de encaminhamento tornam-no uma base sólida e reutilizável — um excelente protótipo para construir um serviço real.

*(Uma versão em inglês deste documento está em `README.md`.)*

Aplicação web que ajuda um utente a decidir **a que unidade de saúde da
Região Autónoma da Madeira se deve dirigir**: faz uma triagem simplificada
por perguntas de sim/não, estima a cor de prioridade (inspirada na Triagem
de Manchester) e recomenda a unidade adequada mais próxima, tendo em conta
os horários de funcionamento.

## Avisos importantes (ler primeiro)

1. **Validação clínica obrigatória.** Os fluxogramas em `app/data/rules/`
   e o mapeamento cor → tipo de serviço em `app/core/routing.py` são
   **exemplos de desenvolvimento**. Antes de qualquer uso com utentes
   reais, têm de ser revistos e aprovados pela equipa clínica do SESARAM.
   Nota: os fluxogramas oficiais da Triagem de Manchester são licenciados
   (Grupo Português de Triagem), esta é uma versão simplificada própria.
2. **Dados das unidades por confirmar.** Em `app/data/unidades.json`, as
   coordenadas são aproximadas e as moradas, telefones, serviços e
   horários estão marcados com `(CONFIRMAR)` e `"dados_confirmados": false`.
   Tudo deve ser confirmado junto do SESARAM antes de qualquer uso real.
3. **Privacidade (RGPD).** A aplicação não guarda dados dos utentes: não
   há base de dados, sessões nem registos de respostas. A localização é
   usada apenas no momento do cálculo e nunca armazenada. Manter assim.
4. A ferramenta **não substitui** avaliação clínica nem a triagem oficial
   feita nas urgências, o disclaimer visível na interface é obrigatório.

## Como correr

Requisitos: Python 3.11 ou superior.

Só na primeira vez, instalar as dependências:

```bash
python -m pip install -r requirements.txt
```

De cada vez que quiseres arrancar o servidor:

```bash
python -m uvicorn app.main:app --reload
```

Usa-se `python -m uvicorn` (e não `uvicorn` diretamente) para funcionar em
qualquer sistema, incluindo Windows, sem depender do PATH.

Depois abrir no browser:

- Aplicação: http://127.0.0.1:8000
- Documentação interativa da API: http://127.0.0.1:8000/docs

Para **parar** o servidor: Ctrl+C no terminal. Depois de alterar o código,
faz **Ctrl+F5** no browser (atualização forçada, para não usar a versão em
cache); a versão em uso pode confirmar-se em http://127.0.0.1:8000/api/saude.

Correr os testes:

```bash
python -m pytest
```

Opcional: para isolar as dependências deste projeto das do resto do
sistema, podes criar um ambiente virtual antes de instalar, com
`python -m venv .venv` e depois ativá-lo (Windows: `.venv\Scripts\activate`;
macOS/Linux: `source .venv/bin/activate`).

## Estrutura do projeto

```
onde-ir-sesaram/
├── app/
│   ├── main.py               # aplicação FastAPI (API + frontend estático)
│   ├── api/routes.py         # endpoints REST
│   ├── models/schemas.py     # validação dos pedidos (Pydantic)
│   ├── core/
│   │   ├── triage_engine.py  # motor de triagem (lê os JSON de regras)
│   │   ├── routing.py        # cor + localização + hora → destino
│   │   ├── horarios.py       # aberto/fechado num dado momento
│   │   ├── geo.py            # distância de Haversine
│   │   ├── unidades.py       # repositório das unidades
│   │   └── cores.py          # cores de Manchester e contactos
│   └── data/
│       ├── rules/            # 1 ficheiro JSON por queixa + red_flags.json
│       └── unidades.json     # unidades de saúde da RAM
├── static/                   # frontend (HTML + CSS + JS puro + Leaflet)
└── tests/                    # pytest (motor, horários, routing, API)
```

## Como funciona (3 blocos)

1. **Triagem**, o frontend pergunta primeiro pelos sinais de emergência
   (`red_flags.json`): qualquer um selecionado → vermelho e 112. Caso
   contrário, o utente escolhe a queixa e responde a perguntas de sim/não.
   As perguntas estão organizadas em 3 fases visíveis na interface:
   1 perguntas gerais, 2 perguntas específicas, 3 avaliação da
   gravidade. O motor é *stateless*: o frontend reenvia todas as
   respostas em cada pedido e devolve a próxima pergunta ou o resultado.
2. **Cor**, o resultado tem uma cor (vermelho, laranja, amarelo, verde,
   azul) com tempo-alvo de observação, mostrada como uma pulseira.
3. **Encaminhamento**, com a cor, a localização e a hora na Madeira,
   `routing.py` escolhe a unidade aberta mais próxima com o serviço certo.
   Exemplo do porquê de a hora importar: um verde às 3 h da manhã não deve
   ser enviado para um centro de saúde fechado, recebe SNS 24 + urgência
   como alternativa.

## Editar ou adicionar regras de triagem

Cada queixa é um ficheiro em `app/data/rules/`. Formato mínimo:

```json
{
  "id": "dor_garganta",
  "nome": "Dor de garganta",
  "descricao": "Dor ao engolir, garganta inflamada.",
  "fonte": "Quem validou e quando",
  "perguntas": [
    {
      "id": "dg_q1",
      "texto": "Tem dificuldade em respirar ou em engolir a própria saliva?",
      "sim": { "resultado": { "cor": "laranja", "motivo": "..." } },
      "nao": { "resultado": { "cor": "verde", "motivo": "...", "nota": "..." } }
    }
  ]
}
```

Regras do formato: cada pergunta tem ramos `sim` e `nao`; cada ramo ou
aponta para outra pergunta (`{"proxima": "id"}`) ou termina
(`{"resultado": {"cor": ...}}`). O servidor **valida tudo no arranque**
(ids únicos, ramos completos, cores válidas, referências existentes) e
recusa arrancar com regras mal formadas. Depois de mexer nas regras,
correr `python -m pytest` e acrescentar um teste por cada caminho
clinicamente importante (ver `tests/test_triage_engine.py`).

Em caso de dúvida clínica, errar sempre **por excesso** de urgência.

## Editar unidades e horários

Em `app/data/unidades.json`, cada unidade tem um dicionário `servicos`
cujos valores são horários num de dois formatos:

```json
{ "tipo": "24h", "texto": "Urgência aberta 24 horas" }

{ "tipo": "semanal", "texto": "Dias úteis, 08:00-20:00",
  "horas": { "seg": ["08:00-20:00"], "ter": ["08:00-20:00"],
             "qua": ["08:00-20:00"], "qui": ["08:00-20:00"],
             "sex": ["08:00-20:00"], "sab": [], "dom": [] } }
```

Serviços reconhecidos pelo encaminhamento: `urgencia_polivalente`,
`urgencia_basica`, `atendimento_urgente`, `consulta_aberta`. Limitação
conhecida: as faixas horárias não podem atravessar a meia-noite, para
"até à meia-noite" usar `"08:00-23:59"`.

**Feriados (novo na v0.4).** Nos feriados nacionais e nos dois feriados
regionais da RAM (1 de julho e 26 de dezembro), os serviços com horário
`"semanal"` contam automaticamente como **fechados** — mesmo que o
feriado calhe a uma quarta-feira. Se um serviço abrir mesmo num feriado,
acrescenta a chave `"feriado"` ao dicionário `horas`, por exemplo
`"feriado": ["09:00-13:00"]`. Os serviços `"24h"` não são afetados.

Como são obtidos (em `app/core/feriados.py`): os feriados de **data fixa**
(Ano Novo, 25 de abril, 1 de julho, Natal, etc.) estão definidos no próprio
programa; os **móveis**, que dependem da Páscoa (Sexta-feira Santa e Corpo
de Deus), são **calculados matematicamente** a partir da data da Páscoa de
cada ano. Não há qualquer ligação a um calendário externo nem à internet:
funciona para qualquer ano e nunca precisa de atualização manual. O
calendário resultante pode ser conferido em `GET /api/feriados?ano=2026`.
Não incluídos, de propósito: feriados municipais (variam por concelho) e
tolerâncias de ponto (Carnaval, 24 e 31 de dezembro) — confirmar com o
SESARAM se afetam horários.

## Ferramentas para quem edita os dados (sem programar)

Depois de editar qualquer JSON (regras ou unidades), verificar tudo com:

```bash
python scripts/validar_dados.py
```

Aponta erros em linguagem simples (faixas horárias mal escritas,
coordenadas fora da RAM, cores inválidas, perguntas em círculo…) e lista
as unidades que ainda têm dados por confirmar, serve de checklist do
levantamento.

Para a sessão de validação clínica, gerar o documento imprimível:

```bash
python scripts/gerar_validacao_clinica.py
```

Cria `docs/validacao_clinica.html`, cada queixa numa página, com as
perguntas numeradas, os desfechos e um bloco de assinatura/data para o
profissional que validar. As correções feitas no papel passam-se depois
para os JSON (atualizando o campo `fonte` com quem validou e quando).

## API (resumo)

- `GET /api/saude`, health check
- `GET /api/queixas`, queixas disponíveis
- `GET /api/red-flags`, sinais de emergência
- `POST /api/triagem`, `{queixa, respostas}` ou `{red_flags}` → pergunta/resultado
- `GET /api/unidades`, todas as unidades
- `GET /api/unidades/proxima?lat&lng&servico&n`, mais próximas
- `POST /api/encaminhamento`, `{cor, lat, lng}` → recomendação completa;
  aceita opcionalmente `quando` (ISO 8601) para simular a hora do cálculo
- `GET /api/contactos`, 112 e SNS 24
- `GET /api/feriados?ano=`, feriados nacionais + regionais considerados
  nos horários

## Modo de demonstração (hora simulada)

Para mostrar na apresentação que a hora importa, abrir a aplicação com
`?hora=...` no endereço, por exemplo:

```
http://127.0.0.1:8000/?hora=2026-06-29T03:00:00
```

O encaminhamento passa a ser calculado como se fossem 3 h da manhã:
um verde deixa de ser enviado ao centro de saúde fechado e passa para
o atendimento urgente 24 h aberto mais próximo. Uma faixa no ecrã
indica que a hora está simulada.

Outros dois momentos que rendem na apresentação (novo na v0.4):

```
http://127.0.0.1:8000/?hora=2026-07-04T15:00:00   (sábado à tarde)
http://127.0.0.1:8000/?hora=2026-07-01T15:00:00   (feriado: Dia da RAM)
```

Num verde, a app explica que é sábado/feriado, diz a que horas reabre o
centro de saúde mais próximo, e apresenta as duas opções: vigiar em casa
com o apoio do SNS 24 ou ir ao atendimento urgente aberto.

## Interface (v0.5): direção "Serviço público"

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

## Novidades da v0.6: tradução, pesquisa e cartões de cuidado

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

## Novidades da v0.7: fluxogramas clínicos e QR de navegação

**Fluxogramas automáticos no documento de validação.** O protocolo de
Manchester é publicado como fluxogramas — e agora o documento de
validação clínica fala essa língua: cada queixa inclui a árvore
desenhada, gerada de `app/data/rules/*.json` por
`app/core/fluxogramas.py`, com os desfechos pintados nas cinco cores e
as perguntas numeradas como na lista. Saltos entre perguntas, caminhos
sem saída ou cores mal atribuídas tornam-se visíveis num relance. O
desenho acontece no navegador (biblioteca Mermaid via CDN), por isso o
documento precisa de internet ao abrir; sem ela, as perguntas numeradas
continuam lá. As fontes de cada diagrama ficam em
`docs/fluxogramas/*.mmd` e podem abrir-se e editar-se visualmente em
https://mermaid.live.

**QR de navegação no resultado.** O cartão da unidade recomendada
mostra um código QR com as direções do Google Maps: aponta-se a câmara
do telemóvel e a navegação abre — útil quando a avaliação é feita num
computador, e sai também na impressão. O código é gerado localmente
(biblioteca `qrcode-generator`, MIT), sem enviar nada para lado nenhum;
se a biblioteca não carregar, o bloco simplesmente não aparece.

## Novidades da v0.8: tempos de espera em tempo real

**De onde vêm.** O SESARAM publica, no sistema SEISRAM, duas páginas
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

## Novidades da v0.9: exportação em PDF e endpoint de integração

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

## Novidades da v0.10: dados confirmados, histórico no dispositivo e inglês completo

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

## Novidades na v0.11: tempos de viagem numa rede calibrada de estradas

**Porquê.** Até à v0.10, "mais próxima" era distância em linha reta, e a
regra experimental de troca somava uma espera real (recolhida do
SEISRAM) a uma viagem adivinhada (linha reta ÷ 50 km/h) — uma medição
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
(`{"minutos", "metodo": "rede"|"osrm"}`), e `GET /api/viagem` expõe o
estimador para inspeção.

**Avaliação honesta.** `python scripts/avaliar_viagem.py` compara os
dois métodos com 16 percursos de referência
(`app/data/percursos_referencia.json`, tempos típicos, por confirmar):
o erro absoluto médio cai de **10,4 min (linha reta) para 1,9 min**, o
pior caso de **24 para 5 min**. Editar os minutos da rede e voltar a
correr o guião é o ciclo de calibração.

## Limitações conhecidas

- Os tempos de viagem vêm de uma **rede simplificada, calibrada à mão**,
  com valores típicos: sem trânsito em tempo real, sem hora de ponta, e
  com os acessos curtos aproximados. São estimativas para ordenar e
  gerir expectativas, não para navegação. Os percursos de referência e
  os minutos da rede estão por confirmar pela equipa.
- Os dados das unidades ainda incluem entradas por confirmar (ver o aviso
  no início e o campo `"dados_confirmados"`).
- As regras de triagem e os textos de aconselhamento são exemplos, ainda
  não validados clinicamente.
- A localização automática, num computador, é estimada pela ligação à
  internet e pode ser pouco precisa; o utente pode sempre corrigi-la
  escolhendo o concelho.
