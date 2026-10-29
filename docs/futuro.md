# Backlog — o que falta para virar produto

> Estado em 2026-10-29. A coleta e a modelagem estão completas; o que segue é a
> distância entre "funciona na minha máquina" e "alguém abre num link".

---

## Feito agora (P0 resolvido)

### ✅ Publicação de artefatos + VACUUM

**Problema:** o `data/ufsm.db` estava com **159 MB** — 108 MB eram páginas livres
de `DELETE`/`INSERT` repetidos. SQLite não devolve páginas ao sistema sozinho.
E o banco inteiro (com 25 MB de texto de ementa e 90 mil linhas do palpite
heurístico) não pode ir para o browser.

**Solução:** `python -m ufsm_speedrun publicar`

| artefato | tamanho | quando carrega |
|---|---|---|
| `ufsm-web.db` | 7,9 MB (2,1 MB gz) | no boot |
| `ementas.db` | 16,1 MB (4,1 MB gz) | no primeiro clique numa cadeira |
| `manifest.json` | — | metadados |

O VACUUM passou a fazer parte do pipeline (banco de trabalho caiu 159 → 51 MB).
O `ementas.db` leva `programa` + `objetivos`; a bibliografia (o maior campo,
~13 MB) fica atrás de `--com-bibliografia`.

**Contrato de consumo:** `docs/nota-frontend.md §7`.

---

## P1 — correção de modelo

### Campus na rota
**Por quê:** 30 cursos ficam fora de Santa Maria (11 EaD, 7 FW, 7 Palmeira,
6 Cachoeira). Hoje o otimizador trata tudo como uma cidade só e pode sugerir
aula em Cachoeira do Sul e outra em Santa Maria no mesmo semestre.
**Esforço:** médio. `curso.campus` já existe; falta decidir a política
(`mesmo_campus` × `livre`) e aplicar no grafo.
**Risco se não fizer:** a rota é fisicamente impossível para 20% dos cursos.

### Pré-requisitos tipos 3/4/5
**Por quê:** 1.308 itens de "período vencido" e 79 de "CH vencida" são
descartados pelo `plan.ts` (decisão consciente, documentada como "sinal fraco").
A agenda pode colocar uma disciplina antes do período exigido.
**Esforço:** médio. Os dados já estão em `prereq_item.numero_referencia`.
**Risco:** agenda otimista demais em cursos com sequência rígida (música, artes).

### Decisão sobre a DCG estratégica
**Por quê:** horas de cota aberta do curso-base podem cobrir qualquer obrigatória
do alvo. É generoso (`Música` sai a 810 h de CC). Não é bug — é regra igual nos
dois lados —, mas é decisão de produto que ninguém tomou formalmente.
**Esforço:** baixo (é uma flag).
**Risco:** números otimistas sem que o usuário saiba.

---

## P2 — engenharia

### Testes automatizados
**Por quê:** só existe `validar`, que checa o banco pronto. Não há teste do
parser da página, da chave de cache, da classificação de terminal nem da
equivalência.
**Esforço:** baixo. Um `pytest` com 10–15 casos de unidade + um teste de fumaça
offline (tudo em cache) já pega o grosso.
**Risco:** regressão silenciosa a cada mudança de coleta.

### Rebuild offline verificado
**Por quê:** o plano promete "o ETL nunca faz request", mas nunca testamos
`init-db --recreate` + `tudo` com a rede desligada de verdade.
**Esforço:** baixo. Um comando `rebuild` e um teste com cache preenchido.
**Risco:** descobrir no dia do deploy que o pipeline depende de rede em algum ponto.

### Backup do artefato
**Por quê:** `data/` é gitignored. Os 187 MB de raw, o banco e as 943
adjudicações existem **só nesse disco**. Se ele morrer: ~4 h de crawl e duas
rodadas de LLM perdidas.
**Esforço:** baixo. Release no GitHub com `ufsm-web.db.gz` + `ementas.db.gz`;
o raw pode ir como artefato comprimido.
**Risco:** perda total do trabalho de coleta.

---

## P3 — produto

### Objetivo formal da rota
"Rota ótima" em quê — semestres, carga horária, número de disciplinas? O front
assumiu semestres. Precisa ser decidido e dito na UI, porque a resposta muda.

### Revisão dos 323 pares "parcial"
Foram julgados como sobreposição relevante, mas não suficientes para dispensar.
Uma segunda passada (ou revisão humana) pode reclassificar parte deles e reduzir
mais a rota. Baixo impacto, alto esforço.

### Deploy e transparência
Onde a dashboard vai viver (GitHub Pages, Vercel, subdomínio)? E o aviso de que
a análise é **teórica**: não há dado de oferta por semestre (turmas) no SIE web,
então a agenda não garante que a disciplina será ofertada naquele semestre.

### Limpeza
`cobertura_curso` existe no schema e está vazia (a view cobre o caso). Remover
ou materializar — hoje é só peso morto no esquema.

---

## Ordem sugerida

1. `publicar` no fluxo do front (feito do lado de cá; integração em andamento)
2. Campus na rota
3. Testes + rebuild offline
4. Release com os artefatos
5. O resto conforme o escopo do produto
