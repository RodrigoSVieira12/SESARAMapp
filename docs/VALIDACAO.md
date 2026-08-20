# Estado da validação

O que neste protótipo está validado, e o que falta. Dirigido a um parceiro
do SESARAM: separa aquilo por que um engenheiro pode responder (o sistema
comporta-se como especificado, verificado por testes) do que só a
instituição pode assinar (o conteúdo clínico e os dados do mundo real).
(English version: `VALIDATION.md`.)

A linha mais importante deste documento é o primeiro item pendente: até os
fluxos clínicos serem revistos e aprovados, **esta ferramenta não pode ser
usada com utentes reais.**

## Legenda

- ☑ **Validado** — feito e verificado (por testes, ou confirmado contra uma
  fonte).
- ☐ **Pendente** — precisa de revisão ou confirmação, pela parte indicada.

## Conteúdo clínico — responsável: equipa clínica do SESARAM

- ☐ **Fluxogramas de triagem** (`app/data/rules/*.json`). Os 56
  fluxogramas de Manchester (1187 discriminadores) e o ecrã de sinais de
  emergência foram importados da tabela de referência e ainda não estão
  validados clinicamente. Têm de ser revistos discriminador a
  discriminador e aprovados. Usar
  `python scripts/gerar_validacao_clinica.py` para gerar
  `docs/validacao_clinica.html` (uma queixa por página, com bloco de
  assinatura/data) para uma sessão de revisão em papel; as correções
  voltam depois ao JSON, atualizando o campo `fonte` de cada ficheiro com
  quem validou e quando.
- ☐ **Mapeamento cor → tipo-de-serviço** e a **política de encaminhamento
  por cor** (`app/core/routing.py`, `app/data/encaminhamento.json`) —
  incluindo a decisão de que vermelho, laranja e amarelo vão diretamente
  para o hospital de referência. Editável sem código; precisa de aval
  clínico.
- ☐ **Textos de autocuidado** (`app/data/autocuidado.json`), mostrados no
  verde e no azul.
- ☐ **Reescritas do aconselhamento ao utente**
  (`app/data/aconselhamento_utente.json`): as frases leigas PT/EN do cartão
  "O que pode fazer". Desde a v0.15.2 cada item tem estado de validação
  próprio (`validado`, `validado_por`, `validado_em`) — a revisão faz-se
  item a item na página interna `/revisao` (que mostra também o que o
  filtro de segurança esconde ao utente) e regista-se no próprio ficheiro,
  aplicando com `python scripts/aplicar_aconselhamento_utente.py`. Em
  produção, `ONDE_IR_APENAS_VALIDADO=1` esconde ao utente tudo o que ainda
  não estiver validado. Estado atual: **0 de 85 itens validados**.
- ☐ **Reescritas das perguntas ao utente**
  (`app/data/perguntas_utente.json`): as 186 frases leigas PT/EN que
  substituem, no ecrã, as perguntas clínicas dos 1187 discriminadores.
  Desde a v0.15.3 cada item tem o mesmo estado de validação por item — a
  revisão faz-se na secção "Perguntas" da página `/revisao` (pergunta
  clínica oficial lado a lado com a reescrita) e regista-se com
  `python scripts/marcar_validado.py perguntas "<texto clínico>" --por
  "Nome"` (sem passo de aplicar). Aqui o risco é menor do que no
  aconselhamento: em produção, `ONDE_IR_APENAS_VALIDADO=1` **reverte** o
  que não estiver validado para a pergunta clínica oficial de Manchester
  (nada é escondido). Estado atual: **0 de 186 itens validados**.
- ☐ **A regra experimental de troca** (preferir uma unidade um pouco mais
  longe quando poupa muito tempo total) — assinalada na interface como
  experimental; precisa de uma decisão clínica sobre se se mantém e com que
  limiares.

## Dados das unidades — responsável: SESARAM + levantamento de dados

- ☐ **Moradas, telefones, serviços e horários** em
  `app/data/unidades.json`, onde estiver marcado `(CONFIRMAR)` /
  `"dados_confirmados": false`. `scripts/validar_dados.py` lista
  exatamente que unidades ainda têm dados por confirmar, como checklist do
  levantamento.
- ☐ **Coordenadas das unidades** — atualmente aproximadas.
- ☐ **Coordenadas dos sítios** (`app/data/localidades.json`) — do
  estagiário, pendentes de confirmação da equipa (ver os campos
  `"pendentes"` / `"verificado"`).
- ☐ **Minutos da rede de estradas e percursos de referência**
  (`rede_viagem.json`, `percursos_referencia.json`) — estimativas
  calibradas à mão, por confirmar.

## Engenharia — responsável: desenvolvimento (verificado aqui)

- ☑ **Integridade dos dados no arranque**: ids únicos, prioridades e
  cores válidas, cor coerente com a prioridade, discriminadores ordenados
  por prioridade; o servidor recusa arrancar caso contrário (ADR 0002).
  Reverificável com `scripts/validar_dados.py`.
- ☑ **Comportamento do encaminhamento** por cores, ilhas, horários,
  feriados, a política de hospital direto e o seu recuo seguro — coberto
  pela bateria de testes (`tests/`).
- ☑ **Explicabilidade**: todos os ramos do encaminhamento devolvem uma
  lista `motivos`; os testes fixam a forma e os motivos por ramo (v0.13.1).
- ☑ **Cobertura de traduções**: `scripts/auditar_traducoes.py` reporta zero
  strings por traduzir, e a CI garante isso.
- ☑ **O PDF de uma página** cabe sempre numa só página, seja qual for o
  desfecho da triagem — fixado por um teste.
- ☑ **Redes de segurança dos tempos de espera**: cache de TTL curto, cache
  negativa, e degradação "indisponível" (nunca números inventados) —
  coberto por testes.
- ☑ **Privacidade nos logs**: um teste garante que o aviso do recuo do
  hospital não contém a localização do utente (ADR 0011).
- ☑ **Bateria de testes**: 408 testes a passar, 92% de cobertura de `app/`
  (`scripts/cobertura_testes.py`).

## Não decidido aqui — para o SESARAM

Estas são escolhas institucionais, não defeitos do protótipo (ver
[`INTEGRACAO.md`](INTEGRACAO.md)): se os tempos de espera vêm de uma API
oficial em vez de scraping; se um OSRM interno substitui a rede de viagem;
se o botão "telefonar à unidade" encaixa nas políticas internas; e se o
histórico no dispositivo fica local ou é integrado.
