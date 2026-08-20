# Guia dos dados — editar regras, unidades e o modo de demonstração

Tudo o que quem edita os dados (idealmente alguém da equipa clínica)
precisa para mudar o comportamento da aplicação **sem tocar em Python**:
as regras de triagem, as unidades e os seus horários, e o modo de hora
simulada usado em apresentações. Mudado do README para aqui na v0.13.1.
(English version: `DATA_GUIDE.md`.)

## Editar ou adicionar regras de triagem

Cada queixa é um ficheiro em `app/data/rules/`, no modelo por
**discriminadores** de Manchester (v0.14.0). Formato mínimo:

```json
{
  "id": "dor_de_garganta",
  "nome": "Dor de garganta",
  "nome_en": "Sore throat",
  "descricao": "Dor ou irritação na garganta.",
  "pediatrico": false,
  "fonte": "Discriminadores de Manchester; por validar",
  "perguntas": [
    {
      "id": "dor_de_garganta_p1_1234",
      "disc_id": 1234,
      "prioridade": "P1",
      "cor": "vermelho",
      "texto": "Compromisso da via aérea?",
      "texto_utente": "A respiração está muito difícil ou ruidosa, como se o ar não passasse bem pela garganta (a roncar ou a gorgolejar)?",
      "texto_en": "Airway compromise?",
      "texto_utente_en": "Is breathing very difficult or noisy, as if air can't pass properly through the throat (snoring or gurgling)?",
      "descricao": "Explicação clínica do discriminador (usada nos fluxogramas; a sua ideia foi integrada em texto_utente)."
    },
    {
      "id": "dor_de_garganta_p3_5678",
      "disc_id": 5678,
      "prioridade": "P3",
      "cor": "amarelo",
      "texto": "Dor moderada?",
      "texto_utente": "Tem dores a sério, que o impedem de fazer algumas coisas do dia a dia?",
      "texto_en": "Moderate pain?",
      "texto_utente_en": "Do you have noticeable pain that stops you doing some everyday things?"
    }
  ]
}
```

Regras do formato: a lista `perguntas` é uma sequência de discriminadores
**ordenados por prioridade** (P1 → P5). Cada um tem `prioridade` (P1-P5),
`cor` (que tem de corresponder à prioridade: P1 vermelho, P2 laranja, P3
amarelo, P4 verde, P5 azul) e `texto`. O `texto` (e o `texto_en`) é a
pergunta **clínica oficial** de Manchester — é o que aparece nos
fluxogramas e no documento de validação clínica. O `texto_utente` (e o
`texto_utente_en`) é a mesma pergunta reescrita em **linguagem do dia a
dia**, já com a descrição integrada — é o que o frontend mostra ao utente
(recuando para `texto` se faltar). A `descricao` (coluna H da tabela de
Manchester) fica guardada para consulta clínica. Não há ramos `sim`/`nao`:
o motor faz uma pergunta por discriminador, da prioridade mais alta para a
mais baixa, e o **primeiro «sim» decide a cor**; se todos forem «não», o
desfecho fica **um nível abaixo do discriminador menos urgente do fluxo,
sem passar de azul**. Um discriminador amarelo (P3) pode ainda declarar
`"destino": "atendimento_urgente"` (exceção de encaminhamento da v0.12.1).

### As perguntas em linguagem do utente (`perguntas_utente.json`)

Desde a v0.15.3, as reescritas leigas das perguntas vivem em
`app/data/perguntas_utente.json` — **é este o ficheiro que a equipa
clínica edita**, sem tocar em código nem no Excel (o mesmo padrão do
aconselhamento na v0.15.2). Cada item é indexado pelo texto clínico exato
do discriminador (espaços colapsados num só) e tem:

- `pt` / `en`: a pergunta reescrita mostrada ao utente em cada língua (o
  `verificar_perguntas.py` exige o par completo);
- `validado`, `validado_por`, `validado_em` (AAAA-MM-DD): o **estado de
  validação clínica por item**, que vive **só neste ficheiro** — as
  regras não o duplicam, de propósito, porque também se editam à mão e a
  cópia dessincronizava-se.

Depois de editar as **frases**, aplicar às regras:

```
python scripts/aplicar_perguntas_utente.py
```

O script refaz apenas `texto_utente`/`texto_utente_en` em todos os
ficheiros de `rules/` (o `texto` clínico fica intocado), é idempotente e
só reescreve os ficheiros que mudaram. Marcar itens como **validados**
não precisa de aplicar nada — o motor lê o estado no arranque — e o mais
prático é nem editar o JSON à mão:

```
python scripts/marcar_validado.py perguntas --listar --contem "dor no peito"
python scripts/marcar_validado.py perguntas "Dor precordial?" --por "Dra. Exemplo"
```

(O mesmo CLI serve o aconselhamento — `marcar_validado.py
aconselhamento ...` — e aí corre o `aplicar` automaticamente para
ressincronizar o SHA-256.)

A política aqui é **diferente** da do aconselhamento, e está escrita no
próprio ficheiro (campo `politica`): para as perguntas, o recuo para o
texto clínico oficial **é seguro** — é a pergunta validada de Manchester.
A reescrita é uma camada de legibilidade, nunca de lógica: a prioridade e
a cor vêm sempre do discriminador oficial. Por isso o
`verificar_perguntas.py` (também no CI) exige **cobertura total** — um
discriminador sem entrada nas reescritas é erro, porque o utente veria o
texto clínico sem ninguém ter decidido isso — e apanha reescritas
dessincronizadas, chaves órfãs e validações incompletas. E, em produção,
o portão `ONDE_IR_APENAS_VALIDADO=1` no ambiente faz o motor **reverter**
as reescritas ainda não validadas para a pergunta clínica oficial (nunca
esconder — esconder uma pergunta mudaria a triagem).

O servidor **valida tudo no arranque** (ids únicos, prioridades e cores
válidas, cor coerente com a prioridade, ordem das prioridades) e recusa
arrancar com regras mal formadas. Os ficheiros de regras podem ser
regenerados a partir da tabela oficial com
`python scripts/importar_manchester.py <tabela.xls> app/data/rules`.
Depois de mexer nas regras, correr `python -m pytest` e acrescentar um
teste por cada caminho clinicamente importante (ver
`tests/test_triage_engine.py`).

Em caso de dúvida clínica, errar sempre **por excesso** de urgência.

## Aconselhamento ao utente ("O que pode fazer")

O ficheiro `app/data/aconselhamento.json` guarda os conselhos práticos
mostrados no ecrã de resultado, organizados por fluxograma e por cor
(v0.15.0). Formato:

```json
{
  "descricao": "...",
  "fluxos": {
    "dor_toracica": {
      "vermelho": {
        "itens": [
          {
            "texto": "Não reativo e não respira: iniciar T-CPR",
            "texto_utente": "Se a pessoa não acorda e não respira, ligue já para o 112 e não desligue: ao telefone ensinam-no a fazer compressões no peito.",
            "texto_utente_en": "If the person does not wake up and is not breathing, call 112 right away and stay on the line: they will guide you through chest compressions."
          }
        ]
      }
    }
  }
}
```

Cada item tem `texto` (o conselho **clínico** tal como está na tabela de
Manchester, para o profissional e para quem integra a API) e, quando
existe uma versão leiga segura, `texto_utente` (a mesma ideia em
**linguagem do dia a dia**) com a variante inglesa `texto_utente_en`
(v0.15.1), escolhida pela aplicação quando a interface está em inglês.
Os itens de cada (fluxo, cor) estão deduplicados, pela ordem de primeira
aparição na tabela.

**Política de segurança (importante).** Ao contrário das perguntas, o
frontend **não** recua para o `texto` clínico: só mostra ao utente os
itens que têm `texto_utente`. Os conselhos que são só do profissional
(avaliar escalas clínicas, isolamento de contacto, ativar meios, fármacos
por nome, contactar o CIAV, enviar a polícia...) ficam **sem**
`texto_utente` de propósito e nunca aparecem ao utente — mostrar uma
instrução clínica crua a um leigo pode ser inseguro. Onde a ação do leigo
difere da do profissional, escreve-se a ação segura em casa (por exemplo,
perante um membro deformado, "não tente endireitar o membro, mantenha-o
quieto", e não "alinhar o membro").

As reescritas em linguagem do utente vivem em
`app/data/aconselhamento_utente.json` (v0.15.2) — **é este o ficheiro que a
equipa clínica edita**, sem tocar em código. Cada item é indexado pelo texto
clínico exato (espaços colapsados num só) e tem:

- `pt` / `en`: a frase mostrada ao utente em cada língua (o
  `verificar_aconselhamento.py` exige o par completo);
- `validado`, `validado_por`, `validado_em` (AAAA-MM-DD): o **estado de
  validação clínica por item**. Enquanto `validado` for `false`, a frase
  conta como proposta; marcá-la `true` exige preencher quem e quando.

Depois de editar (corrigir uma frase, marcar um item como validado),
aplicar às regras **sem precisar do Excel**:

```
python scripts/aplicar_aconselhamento_utente.py
```

(Para marcar validações, o atalho é `python scripts/marcar_validado.py
aconselhamento "<texto clínico>" --por "Nome"` — grava os três campos e
corre o `aplicar` automaticamente; v0.15.3.)

O script refaz apenas a camada do utente do `aconselhamento.json` (o
`texto` clínico fica intocado), é idempotente, e grava em
`fonte.reescritas` o SHA-256 do ficheiro editável — se alguém editar as
reescritas e se esquecer de o correr, o verificador falha no CI com a
indicação do que fazer. O `aconselhamento.json` é, por isso, um ficheiro
**gerado**: não editar à mão (o verificador também apanha isso). O bloco
`fonte.tabela` regista de que Excel exato os conselhos vieram (nome,
SHA-256, data, nº de linhas) e é preenchido pelo
`scripts/importar_aconselhamento.py <tabela.xls>` quando a própria tabela
mudar; o importador imprime a cobertura (quantos itens já têm versão de
utente) e a lista dos itens ainda sem versão, por frequência, para
orientar quem quiser alargar a cobertura. Como o autocuidado, estas
frases (nas duas línguas) **aguardam validação clínica** antes de uso
real — e, em produção, o portão `ONDE_IR_APENAS_VALIDADO=1` no ambiente
faz o motor esconder ao utente tudo o que ainda não estiver `validado`
(o texto clínico continua a ir para os integradores).

### Vista de revisão (`/revisao`)

Quem revê o ecrã do utente não via o que o filtro de segurança esconde —
e por isso não conseguia confirmar que o filtro acerta. A página interna
`/revisao` (v0.15.2) mostra, por fluxo e cor, o conselho clínico lado a
lado com a reescrita PT/EN, o estado de validação de cada item e, a
cinzento, os itens **ocultos ao utente**; tem filtros (só ocultos, só por
validar, procurar) e lê os dados do disco a cada refresh
(`GET /api/aconselhamento/revisao`). Desde a v0.15.3 tem duas secções: o
**Aconselhamento** e as **Perguntas** (`GET /api/perguntas/revisao`),
esta com a pergunta clínica oficial lado a lado com a reescrita PT/EN e o
estado de validação por item — nas perguntas nada é oculto, por isso o
filtro "só ocultos" não se aplica. É a ferramenta pensada para a sessão
de validação clínica item a item.

### Autocuidado × aconselhamento: como se relacionam

Há dois blocos de conselhos ao utente, com papéis diferentes e que podem
aparecer no mesmo ecrã: o **autocuidado** (`autocuidado.json`) é genérico
por **cor** (verde/azul) — o que fazer/evitar em casa e os sinais de
alarme —, aparece no ecrã de encaminhamento; o **aconselhamento**
(`aconselhamento.json`) é específico do **fluxo e cor** apurados, vem da
tabela de Manchester e aparece no resultado (e no fim do encaminhamento).
A relação ainda **não está reconciliada clinicamente**: o
`verificar_aconselhamento.py` lista como AVISO as frases muito parecidas
entre os dois (mesma cor), para a revisão clínica decidir se a
redundância é desejada ou se um dos lados deve ceder — essa decisão é
clínica e fica de fora do CI de propósito.

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
- `GET /api/fluxogramas?idioma=pt|en`, fluxogramas Mermaid das regras
  atuais, relidos do disco a cada pedido (v0.12; suporta a
  pré-visualização viva em `/fluxogramas`)
- `POST /api/triagem`, `{queixa, respostas}` ou `{red_flags}` → pergunta/resultado
- `GET /api/unidades`, todas as unidades
- `GET /api/unidades/proxima?lat&lng&servico&n`, mais próximas
- `GET /api/viagem?lat&lng&lat_destino&lng_destino`, tempo de viagem de
  carro estimado entre dois pontos (inspeção; v0.11); com `&unidade=<id>`
  em vez das coordenadas de destino, a tabela local de tempos por
  estrada pode responder (método "medido"; v0.11.3)
- `GET /api/localidades`, árvore concelho → freguesia → sítio para o ecrã
  de localização manual (v0.11.1)
- `GET /api/espera?atualizar=`, tempos de espera em tempo real (cache do SESARAM)
- `POST /api/encaminhamento`, `{cor, lat, lng}` → recomendação completa
  (com o bloco `politica` aplicado); aceita opcionalmente `quando`
  (ISO 8601) para simular a hora do cálculo e `destino` (v0.12.1, só
  amarelo), vindo do desfecho do fluxograma
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
