# Dashboard — decisões, algoritmo e limites

> Frente **(B) frontend**. Contrato de dados em `docs/frontend-contrato.md`.
> Este documento registra o que foi decidido na implementação e por quê.
> Última atualização: 2026-10-28.

## 1. Decisão de arquitetura: tudo no cliente

`docs/plano.md` §8 previa FastAPI + Jinja2. A implementação seguiu outro
caminho, por decisão de produto: **o usuário baixa o `ufsm.db` e o site roda
sozinho**.

- `sql.js` (SQLite compilado para WebAssembly) abre o arquivo escolhido
  (`<input type=file>`, drag & drop ou `./ufsm.db` ao lado da página).
- O banco vira estruturas em memória uma única vez (~12 mil ofertas; leitura
  completa em poucas centenas de ms).
- Nenhuma query no servidor, nenhuma request para a UFSM. O site é estático
  (`dist/`) e funciona offline.
- Nada é escrito no banco: a `Database` do sql.js é uma cópia em memória.

Consequência prática: o deploy é arrastar `dist/` para qualquer host (ou abrir
com um servidor estático local). O único cuidado é o WAL — use
`web/scripts/snapshot-db.py`, que copia via backup API do SQLite.

## 2. Modelo em memória

```
Universe
├ cursos: CourseModel[148]
│  ├ curso, versao (selecionada=1)
│  ├ ofertas (todas as 12.313, agrupadas por versão)
│  ├ fixed: obrigatórias (tipo_item = 1), deduplicadas por disciplina
│  ├ quotas: núcleos com ch_minima > obrigatórias do núcleo
│  ├ prereqs/equivals: por disciplina (LEFT JOIN tolerante a dado parcial)
│  └ cargaSemestre: ch_max_periodo (ou mediana observada)
└ cursosByDisc: disciplina -> cursos que a listam
```

Pontos que exigiram cuidado:

1. **Hierarquia de `estrutura`** (`pai_id`): se um ancestral já tem cota
   (`ch_minima > 0`), a cota do filho não é contada de novo — senão o déficit
   dobrava em cursos como Jornalismo/FW.
2. **Mesma disciplina em dois núcleos** da mesma versão: a CH entra uma vez só.
3. **Cotas** — três tipos, com semânticas diferentes:
   - `dcg`: o núcleo tem ofertas `tipo_item = 5/7`. DCG, por definição, aceita
     qualquer disciplina do catálogo → o histórico do aluno (inclusive as horas
     de DCG do curso de origem) preenche a cota.
   - `eletiva`: o núcleo lista optativas/eletivas (tipo 2/3) e **só elas**
     valem. Sem isso, qualquer curso com muito "núcleo flexível" ficava
     artificialmente barato.
   - `livre`: cota sem nenhuma disciplina listada (as ~21 cotas abertas do
     relatório de qualidade) → horas de eletiva a escolher, 60 h por cadeira
     sintética.
   - `atividade`: atividades complementares/extensão entram como custo à parte,
     nunca como disciplina nem dentro dos semestres.
4. **`periodo_ideal = 99`** → "qualquer", coluna própria no grafo e no
   planejamento.

## 3. Cálculo do custo de um curso-alvo

Entrada: `done` = disciplinas cumpridas + horas de eletiva "sem identidade"
(as cotas já fechadas do curso de origem, proporcionais ao progresso).

```
cobertas        = obrigatórias do alvo ∩ done
por_equivalência = obrigatórias do alvo cujo equivalencia_item aponta para algo em done
faltam          = obrigatórias - cobertas - por_equivalência
surplus         = horas livres + CH de done que o alvo não exige
para cada cota:
    dcg/livre  -> preenche com surplus
    eletiva    -> preenche só com candidatas de done que estão na lista
extra_CH        = CH(faltam) + cotas não preenchidas
extra_cadeiras  = |faltam| + ceil(cotas_restantes / 60)
semestres       = tamanho do plano (bin-packing)
```

**Plano semestral (heurística):** cada disciplina faltante recebe o semestre
mais cedo possível a partir dos pré-requisitos oficiais (OR entre blocos, AND
dentro do bloco; pré-requisito fora do currículo-alvo é ignorado). Depois as
disciplinas são empacotadas em semestres respeitando `cargaSemestre`. Ciclos de
pré-requisito caem num bloco final em vez de travar.

**DCG estratégica (o "pulo do gato"):** as horas de DCG/cota aberta do curso de
origem aceitam **qualquer disciplina do catálogo**. Então elas podem ter sido
gastas justamente nas obrigatórias que faltam no curso-alvo — é o mecanismo que
faz "terminei CC e no semestre seguinte fechei SI". A regra:

```
livre = horas de DCG/cota aberta do curso-base (freeAberto)
para cada obrigatória do alvo que falta, da maior CH para a menor:
    se cabe em livre: conta como cumprida (badge DCG)  e livre -= CH
o resto de livre + as disciplinas do aluno fora do alvo formam o pool das cotas
```

Menu fechado (`eletiva` de núcleo) **não** entra nessa conta: só vale a lista do
núcleo. O interruptor "DCG estratégica" na barra lateral liga/desliga (default
ligado; é uma escolha que o aluno faz, não um fato).

O bin-packing usa a CH máxima oficial como teto — por isso um curso de 58
cadeiras pode fechar em ~6 semestres. É uma estimativa otimista e explícita:
não modela oferta de turma, choque de horário, estágio obrigatório presencial
nem pré-requisito que a coleta ainda não trouxe.

**Matriz 148×148 (aba Mapa):** mesma conta sem montar o plano
(`ceil(extra_CH / carga)`), ~22 mil células, calculada em uma passada.

## 4. Equivalência

Usada em dois lugares:

1. **Cobertura**: obrigatória do alvo com `equivalencia_item` apontando para
   disciplina que o aluno já tem conta como cumprida (badge `equiv`).
2. **Grafo**: aresta tracejada quando as duas disciplinas estão no mesmo
   currículo.

A equivalência heurística por ementa (≥ 75%) **não** entra no cálculo — só a
oficial. Quando a Fase 4 terminar, o caminho natural é a Fase 6a gravar
`similaridade_ementa` e a UI passar a marcar `via = heuristica` com veredito
visível.

## 5. UI

- `web/src/db/load.ts` — uma passada por tabela → `Universe`.
- `web/src/lib/plan.ts` — `makeDone`, `scoreCourse`, `planSemesters`,
  `rankCourses`, `buildMatrix`, `leverInsights`.
- `web/src/lib/graph.ts` — grafo de pré-requisitos (colunas por período) e rede
  bipartida curso ↔ disciplina (só disciplinas compartilhadas por ≥ 3 cursos,
  top 36 por grau).
- `web/src/components/*` — DbGate, BasePanel, Ranking, CourseDetail, Graph,
  Matrix, Metodo.
- Estado da URL: `#b=<curso>&t=<alvo>&a=<aba>` (compartilhável).
- `?db=<url>` escolhe outro banco.

## 6. Limites conhecidos (e o que fazer depois)

| limite | impacto | próximo passo |
|---|---|---|
| pré-requisitos ~25% das ofertas | plano semestral otimista | nada no front; depende da Fase 3 |
| **equivalências gravadas sem disciplina** | **métrica subestimada hoje** — ver §8 | corrigir parser e reprocessar o raw |
| ementas quase vazias | nenhum (ainda não usadas) | Fase 6a + badge na UI |
| reformas trocam códigos | queda brusca de sobreposição (ex.: CC/2026) | equivalência oficial resolve (quando consertada) |
| oferta de turma/horário não modelada | semestres otimistas | integrar horários (não existe no SIE público) |
| cota restrita usa só o menu do núcleo | pode subestimar equivalência aprovada caso a caso | revisão humana da Fase 6a |
| DCG estratégica é uma escolha do aluno | cenário otimista (mas realista se planejado) | interruptor na UI; default ligado |

O front é **tolerante a dado parcial**: `LEFT JOIN` em tudo, estados vazios
explícitos ("a coleta ainda não chegou neste curso"), e o topo mostra a
porcentagem de ofertas com pré-requisito. Reexportar o banco melhora os números
sem mexer no código.

## 8. Bug encontrado na coleta (para a frente A)

`equivalencia_item` tem 4.862 linhas **todas com `disciplina_req_id` e
`disciplina_req_codigo` nulos**: o parser lê `item["disciplinaRequisito"]`
(campo de pré-requisito), mas a API de equivalências devolve a disciplina em
`item["disciplina"]`. O `data/raw/` já tem o dado (5.007 pares!), então é
reprocessar — **não precisa de novo crawl**.

Impacto medido nos brutos de hoje (partindo de CC):

| curso | obrigatórias | cobertas por equivalência com CC |
|---|---|---|
| Sistemas de Informação | 37 | **14** |
| Engenharia de Computação | 59 | 9 |
| Engenharia de Produção | — | 6 |

Com isso CC→SI sai de ~1.470 h / 3 semestres (DCG estratégica) para ~900 h /
2 semestres. O `prereq_*` está correto (99% das ofertas com pré-requisito já têm
blocos), então a correção é pontual.

Patch sugerido em `ufsm_speedrun/relacoes.py` (linha ~52):

```python
req = item.get("disciplinaRequisito") or item.get("disciplina") or {}
```

## 7. Run completo (aba `Todos`)

Pergunta: "e para fazer **todos** os outros?". `lib/speedrun.ts` monta a rota.

- **Pool** = tudo que o aluno já tem (`done.ids` + horas de eletiva).
- **Custo marginal** de um curso = as mesmas regras do §3, mas com o pool no
  lugar de `done`: obrigatórias que faltam, equivalências oficiais, cotas DCG/
  abertas preenchidas pelo excedente do pool e cotas de menu fechado preenchidas
  com as candidatas mais "compartilhadas" (mais cursos listam → mais útil).
- A **DCG estratégica** do curso-base é materializada nas obrigatórias do
  primeiro curso que ela ajuda (480 h ≈ 8 cadeiras no caso CC→SI).
- **Rota gulosa**: a cada passo escolhe o curso de menor custo marginal
  (horas, depois nº de cadeiras). O curso escolhido fecha; os que já estavam
  cobertos entram como passos de 0 h.
- As cadeiras novas do passo entram no pool — é isso que faz os cursos
  seguintes ficarem mais baratos.

Fatos que a tela deixa explícitos:

- **O total não depende da ordem** (união de conjuntos). A ordem muda só *quando*
  cada curso fecha; a rota gulosa minimiza cada passo.
- Com Ciência da Computação como base: **5.219 cadeiras distintas**, **314.395 h**
  extras, **~583 semestres (~292 anos)** — 4.375 cadeiras pertencem a um único
  currículo e só 750 aparecem em 2+ cursos. Metade das horas está nos primeiros
  98 cursos; a cauda é Medicina/Veterinária/Agronomia.
- A curva (barras = custo do passo, linha = acumulado) mostra o "degrau" que
  cada curso caro impõe.

Limites: o run inteiro não simula pré-requisitos (seria uma árvore de 5 mil
nós); o semestre de fechamento é `CH acumulada ÷ carga média`. Cada passo
individual continua tendo o plano completo na aba **Curso**.
