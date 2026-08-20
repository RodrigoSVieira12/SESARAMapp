# Fonte dos discriminadores de Manchester

Este diretório guarda a tabela de referência a partir da qual são gerados
os fluxogramas de triagem em `app/data/rules/`.

- `Table_Motivo_Prioridade_Discriminadores.xls` — tabela oficial com, por
  linha: fluxograma, prioridade (P1–P5), id do discriminador, texto do
  discriminador e descrição clínica (coluna H).

## Regenerar as regras

```bash
pip install pandas xlrd     # dependências só do importador (não da app)
python scripts/importar_manchester.py \
    docs/manchester/Table_Motivo_Prioridade_Discriminadores.xls \
    app/data/rules
```

O importador (`scripts/importar_manchester.py`):

- ignora as linhas que não são discriminadores de sim/não — o divisor
  «------- LIMITE RISCO -------», o marcador do desfecho P5 «Sem
  discriminador Positivo» (que passa a ser o recuo automático para azul) e
  a instrução «USE OUTRO DISCRIMINADOR»;
- mapeia cada prioridade para a sua cor de Manchester (P1 vermelho, P2
  laranja, P3 amarelo, P4 verde, P5 azul);
- traduz os 186 textos únicos de discriminador e os 56 nomes de fluxo para
  inglês (dicionários curados em `scripts/_manchester_traducoes.py` e
  `scripts/_manchester_fluxos.py`);
- guarda a descrição clínica no campo `descricao` de cada discriminador
  (mostrada ao utente como ajuda da pergunta).

É reexecutável e idempotente: apaga e regenera `app/data/rules/*.json`
(exceto `red_flags.json`).

> **Aviso:** os discriminadores vêm tal e qual da tabela e ainda exigem
> validação clínica antes de qualquer uso real (ver `docs/VALIDACAO.md`).
