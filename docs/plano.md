# ufsm-speedrun — plano do projeto

> Documento de retomada. Se o chat for perdido, comece lendo este arquivo e
> `docs/ufsm-api.md`. Tudo que foi decidido e descoberto está aqui.

Última atualização: 2026-10-28 · status: **Fases 0, 1 e 2 concluídas** ·
Fases 3 e 4 implementadas (crawl longo pendente) · Fases 5–7 a fazer

---

## 1. O problema

Estudante da UFSM quer descobrir a **rota ótima para cumprir todos os cursos de
graduação** partindo de um curso inicial, aproveitando cadeiras já cumpridas
(mesma disciplina em outro curso + equivalências).

Perguntas que o produto responde:
- "Cursando Ciência da Computação, quantos semestres a mais para eu também fechar
  Engenharia de Computação?"
- "Quais cadeiras eu já matei de graça por equivalência?"
- "Qual disciplina é o gargalo que destrava mais cursos?"

## 2. Insumos

| Fonte | Uso |
|---|---|
| `https://www.ufsm.br/graduacao` | lista dos 110 cursos |
| `.../cursos/graduacao/<campus>/<slug>/informacoes-do-curriculo` | IDs de curso + versões |
| webservice SIE em `portal.ufsm.br` | **todo o dado curricular** (JSON) |

Detalhes de endpoints, headers, enums e armadilhas: **`docs/ufsm-api.md`**.
Resumo: 7 endpoints POST, header `X-UFSM-Application-ID: SiteWS`, sem token.

## 3. Decisões já tomadas

| Tema | Decisão |
|---|---|
| Extração | API JSON do SIE, **não** scraping de HTML (HTML só p/ descobrir IDs) |
| Banco | SQLite (`data/ufsm.db`), schema em `ufsm_speedrun/schema.sql` |
| Rastreabilidade | toda request+response gravada em `data/raw/` + log em `data/logs/requests.jsonl` |
| Recrawl | nunca necessário: ETL lê `data/raw/` |
| Polidez | 1 request por vez, ≥1,75 s, backoff, UA identificável, fora de horário comercial |
| Dependências | stdlib only na Fase 0; `beautifulsoup4` a partir da Fase 1 |
| Ambiente | `.venv/` no projeto |
| Layout | pacote flat `ufsm_speedrun/` (sem `pip install -e`) |

### Decisões já resolvidas

- **Cursos**: todos os **148** (não 110 — a página tem 103 URLs, mas cada URL pode
  expor vários cursos). 5 campi + EaD. Campus é gravado por curso (`curso.campus`).
- **Versões**: as 528 são coletadas na Fase 1 (é barato e fica no cache). A Fase 2
  processa por padrão só as **148 selecionadas** (`Corrente`, com fallback para a
  `Ativa` mais recente). Histórico completo: `curriculos --todas`.
- **Fase 4 (ementas)**: só disciplinas alcançáveis pelas versões selecionadas —
  evita pagar por disciplina morta de currículo antigo.

### Decisões ainda em aberto

1. **Função objetivo da rota**: minimizar nº de semestres, CH total, ou nº de disciplinas?
2. **Equivalência heurística**: usar só `programaDisciplina` (tipo 2) ou incluir
   `objetivos` no texto comparado? (recomendo os dois, com pesos diferentes)
3. **Política de campus** no otimizador: `mesmo_campus` (default) ou `livre`.
   EaD tratado como campus próprio.

## 4. Arquitetura

```
ufsm-speedrun/
├── .venv/                      # ambiente (gitignored)
├── ufsm_speedrun/
│   ├── __init__.py
│   ├── __main__.py             # python -m ufsm_speedrun
│   ├── config.py               # caminhos + constantes + política de acesso
│   ├── endpoints.py            # URLs, enums do SIE
│   ├── recorder.py             # envelope request+response, cache, log
│   ├── http.py                 # UfsmClient (pacing, retry, cache, GET/POST)
│   ├── persist.py              # upsert de disciplina (compartilhado)
│   ├── db.py                   # conexão, init, contagens
│   ├── schema.sql              # esquema completo
│   ├── discover.py             # fase 1
│   ├── curriculos.py           # fase 2
│   ├── relacoes.py             # fase 3
│   ├── ementas.py              # fase 4
│   └── cli.py                  # init-db | smoke | discover | curriculos |
│                               # relacoes | ementas | tudo | stats
├── docs/
│   ├── ufsm-api.md             # engenharia reversa da API
│   └── plano.md                # este arquivo
└── data/                       # gitignored, gerado
    ├── raw/<endpoint>/<key>.json   # envelope: request + response + meta
    ├── logs/requests.jsonl         # auditoria append-only (sem corpo)
    └── ufsm.db
```

### Fluxo de dados

```
site (HTML) ──┐
              ├─► UfsmClient ──► data/raw/**  ──► ETL (Fase 5) ──► ufsm.db
SIE (JSON) ───┘        │
                       └─► data/logs/requests.jsonl
```

Regra de ouro: **a rede é uma fase separada do banco.** O ETL nunca faz request;
só lê `data/raw/`. Assim dá para reescrever o schema e reprocessar em segundos.

### Chave de cache

`sha256(method + url + params canônicos)[:16]` → mesmo pedido, mesmo arquivo.
`--refresh` sobrescreve.

## 5. Fases

### ✅ Fase 0 — esqueleto (concluída)

Entregue:
- venv + `requirements.txt`
- `UfsmClient` com pacing, backoff, cache em disco e logging
- envelope `ufsm-sie-raw/1` (request + response + `body_sha256`)
- `schema.sql` completo (14 tabelas + 1 view)
- CLI `init-db`, `smoke`, `stats`
- `docs/ufsm-api.md`

Critério de aceite (atingido): `smoke` faz 1 request, grava o raw, e a segunda
chamada vem do cache com hash íntegro.

### ✅ Fase 1 — descoberta de cursos e versões (concluída)

Comando: `python -m ufsm_speedrun discover`

Resultado real:
- 103 páginas visitadas, **148 cursos**, **528 versões**, 0 erros
- 148 versões selecionadas (uma por curso), **0 fallbacks** — todo curso tem Corrente
- anos das selecionadas: 2004 a 2027
- 10,5 MB, 261 s (≈1,75 s/request)

Achados: uma página ≠ um curso (`musica` = 20 cursos); `numero` nem sempre é ano.

### ✅ Fase 2 — árvores curriculares (concluída)

Comando: `python -m ufsm_speedrun curriculos` (148 versões selecionadas)

Resultado real:
- 148/148 versões, 0 erros
- **1.574** nós de estrutura, **2.367** atividades, **12.313** ofertas de disciplina
- **8.259** disciplinas distintas
- 39 MB, 662 s

Distribuição das ofertas: 6.968 obrigatórias, 4.884 DCG, 426 eletivas, 16 optativas,
14 DCG de pós, 3 atividades, 2 inativas.

Checkpoint dos buckets abertos: 245 cotas fechadas por atividades complementares e
**21 cotas realmente abertas** (sem disciplinas e sem atividades) — ex.: DCG de 420 h
em Sistemas de Informação/2026 e Engenharia de Transportes e Logística/2023.

### Fase 3 — pré-requisitos e equivalências

- para cada `disciplina_curriculo` com `tem_prereq`/`tem_equiv`:
  `POST curso/preRequisitosAgrupados.json` e/ou `.../equivalenciasAgrupadas.json`
- popular `prereq_bloco`/`prereq_item` e `equivalencia_bloco`/`equivalencia_item`
- comando: `python -m ufsm_speedrun relacoes`
- **retomável**: reprocessar é barato (cache), e falha não grava nada

Volume real: **6.031 ofertas** com alguma relação → ~7,2 mil requests rápidos
(≈0,1 s) ≈ **3,5 h** a 1,75 s.

### Fase 4 — ementas

- catálogo único de códigos: **8.259** (não 3–4 mil como estimado)
- `POST disciplina/disciplina.json` por código
- normalizar HTML → texto; separar `programa_texto` (tipo 2, recursivo) de
  `bibliografia_texto` (tipo 1); guardar `objetivos_html` bruto
- comando: `python -m ufsm_speedrun ementas` (pula quem já tem `raw_file`)
- **checkpoint**: nº de disciplinas sem programa (varia muito: amostra deu 2/3 sem)

Volume real: 8.259 requests (~0,1 s, ~6 KB) ≈ **4 h** a 1,75 s. É o gargalo.

### Estado do banco (2026-10-28)

| tabela | linhas |
|---|---|
| `curso` | 148 |
| `versao_curriculo` | 528 (148 com `selecionada=1`) |
| `estrutura` | 1.574 |
| `estrutura_atividade` | 2.367 |
| `disciplina` | 8.259 (só 3 com ementa — Fase 4 pendente) |
| `disciplina_curriculo` | 12.313 |
| `prereq_*` / `equivalencia_*` | parciais (amostra de 6 ofertas) |

Pendente para fechar a coleta: `relacoes` (~3,5 h) + `ementas` (~4 h) a 1,75 s.
Com `--delay 0.8` cai para ~1,6 h + ~1,9 h. Ambos são retomáveis.

### Fase 5 — ETL e validação

- consolida o que as fases anteriores gravaram (ou reprocessa `data/raw/` do zero)
- comando: `python -m ufsm_speedrun load --from-raw`
- checagens automáticas:
  - integridade referencial (todas as FK resolvem)
  - soma de CH das obrigatórias vs `versao_curriculo.ch_total`
  - ciclos no grafo de pré-requisitos
  - disciplinas órfãs (em currículo mas sem ementa)
  - duplicidade `(versao, estrutura, disciplina)`
- saída: `docs/relatorio-qualidade.md` gerado

### Fase 6a — equivalência heurística

Regra do projeto (definida pelo usuário):
> Candidato a equivalente se `ch_do_alvo <= ch_do_candidato` **e** similaridade de
> ementa **≥ 75%**.

Implementação:
1. tokenizar `programa_texto` + `objetivos` (lowercase, sem stopwords PT, stemming leve)
2. TF-IDF + similaridade de cosseno (par a par dentro do mesmo "cluster" de
   nome/código, para não comparar 4 mil × 4 mil = 16 M pares)
3. complemento: Jaccard de tokens
4. gravar em `similaridade_ementa` com `veredito`
5. **revisão humana**: gerar tabela `docs/revisao-equivalencias.md` com os pares
   de score entre 0,6 e 0,85 — a faixa perigosa

### Fase 6b — otimizador de rota

Modelo:
- `Nó` = `disciplina` global (cursar uma vez serve para vários cursos)
- `Aresta` dura = pré-requisito (raro — usar quando existir)
- `Aresta` branda = `periodo_ideal` (sequenciamento recomendado)
- `Requisito` = árvore: AND entre nós; cada nó é
  `(lista de disciplinas) + cota de horas/créditos` → **mochila**
- `Objetivo` = função escolhida em §3 (semestres / CH / nº disciplinas)

Abordagem sugerida: começar com heurística gulosa por "grau de destrave"
(quantos cursos a disciplina destrava ÷ custo em horas), com validação de
pré-requisitos por ordenação topológica; se preciso, ILP com OR-Tools depois.
A heurística já responde 90% das perguntas e é explicável na dashboard.

## 6. Regras de negócio (resumo)

1. **Disciplina é global; oferta é local.** `ELC1079` cursada uma vez conta em
   todos os currículos que a listam.
2. **Equivalência não funde disciplinas** — é aresta com direção e bloco
   (OR de blocos, AND dentro do bloco).
3. **Requisito é lista + cota.** Um núcleo "≥1200 h" não é "cursar 19 cadeiras";
   é escolher o subconjunto que fecha a cota.
4. **Cota aberta** (DCG sem disciplinas listadas) = qualquer disciplina do
   catálogo, respeitando tipo/período. Precisa de tratamento explícito.
5. **Pré-requisito oficial é incompleto.** Não inventar; usar `periodo_ideal`
   como sinal brando e registrar a limitação na UI.
6. `versao_curriculo.situacao = 'Corrente'` é o que vale para análise.

## 7. Convenções

- **Commits**: `fase<N>: <descrição>` (ex.: `fase2: crawl das árvores curriculares`).
- **Nunca** commitar `data/`.
- Todo request novo **tem** que passar por `UfsmClient` (nunca `urllib` solto),
  senão perde cache/log.
- Novos endpoints/enums: documentar em `docs/ufsm-api.md` **antes** de codar.
- Datas em UTC ISO-8601.

## 8. Client web (Fase 7) — dashboard

**Requisito duro: zero request para a UFSM.** Lê apenas `data/ufsm.db` em
modo read-only. Se a rede estiver desligada, a dashboard funciona igual.

### Stack

- **FastAPI** + Jinja2 (server-side rendering) — sem build de front-end
- **Cytoscape.js** para o grafo, **Chart.js** para os gráficos
- bibliotecas **vendorizadas** em `web/static/vendor/` (nada de CDN → offline)
- SQLite aberto com `file:ufsm.db?mode=ro` e `PRAGMA query_only=ON`
- uma única dependência extra: `fastapi`, `uvicorn`, `jinja2`

### Views

| View | Rota | Conteúdo |
|---|---|---|
| **Visão geral** | `/` | KPIs (cursos, disciplinas únicas, ofertas, % com prereq, nº de DCG abertos), tabela de cursos com filtro por campus/modalidade |
| **Curso** | `/curso/{id}` | árvore de núcleos (accordion) + tabela de cadeiras por período com badges de pré-req/equiv + barra de "cota do núcleo vs. CH listada" |
| **Grafo** | `/grafo?curso={id}` | Cytoscape: nós = disciplinas, cor por `tipo_item`, aresta sólida = pré-requisito, tracejada = equivalência, tamanho do nó ∝ CH; clique abre painel lateral |
| **Planejamento** | `/rota` | escolhe curso inicial + cursos-alvo → linha do tempo por semestre, CH por semestre, disciplinas reaproveitadas destacadas |
| **Equivalências** | `/equivalencias` | pares candidatos com score de ementa, filtro "≥75%", botão de marcar como confirmado/rejeitado |
| **Qualidade** | `/qualidade` | contagens do crawl, integridade, lista de buckets abertos e disciplinas sem ementa |

### API interna (JSON, mesma fonte)

```
GET /api/kpis
GET /api/cursos?campus=&modalidade=
GET /api/curso/{id}
GET /api/curso/{id}/grafo
GET /api/grafo?cursos=1,2,3
GET /api/rota?inicial=701&alvos=1250,1251
GET /api/equivalencias?min_score=0.75
```

### Cuidados

- consultas pesadas (grafo, rota) → cache em memória + `@lru_cache` por params
- `cobertura_curso` pré-calculada na Fase 5/6 (não calcular na request)
- estados vazios explícitos ("banco não ingerido — rode `load`")
- tema escuro por padrão, tipografia decente; é o cartão de visita do projeto

## 9. Como retomar em um chat novo

Cole isto:

```
Projeto em C:\Users\Rodrigo\pessoal\projetos\ufsm-speedrun
Leia docs/plano.md e docs/ufsm-api.md antes de qualquer coisa.
Ambiente: .venv (Python 3.12). Rodar: .\.venv\Scripts\python.exe -m ufsm_speedrun <cmd>
Estado: fases 0,1,2 concluídas; 3 e 4 implementadas (crawl longo pendente).
Comandos: init-db | smoke | discover | curriculos | relacoes | ementas | tudo | stats
Regras: toda request passa por UfsmClient; raw em data/raw; ETL nunca faz request;
        nunca commitar data/; commits no formato "fase<N>: <descrição>".
```

## 10. Riscos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Site muda de layout/API | baixa | alto | cache em `data/raw` + doc da API + detecção de `validate`/`error` |
| Bloqueio por excesso de requests | baixa | alto | pacing 1,75 s, sem paralelismo, fora de horário comercial |
| DCG sem lista (cota aberta) | alta | alto | modelado como bucket aberto; tratar na Fase 6 |
| Pré-requisitos incompletos | alta | médio | `periodo_ideal` como sinal brando; documentar |
| Universo de pares de ementas explodir | média | médio | bloquear comparação por cluster de nome/código |
| Escopo "todos os cursos" inviável na prática | média | baixo | é análise teórica; declarar premissas na UI |

---

## 11. Fase 7 executada — dashboard client-side (2026-10-28)

O §8 descrevia FastAPI + Jinja2. A dashboard foi implementada **sem servidor**:
`web/` (React + Vite + sql.js + Cytoscape) abre `data/ufsm.db` no navegador e
calcula tudo no cliente — o produto é "baixe o banco e abra o site".

- modelo de dados, semântica das cotas (DCG / eletiva de núcleo / cota aberta),
  custo de fechar um curso e plano semestral: `docs/frontend.md`
- contrato com a coleta: `docs/frontend-contrato.md`
- como rodar: `web/README.md` (`snapshot-db.py` aplica o WAL; `npm run dev`)

O banco é read-only: nenhuma query volta para a UFSM e nada é gravado.
