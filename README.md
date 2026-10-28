# ufsm-speedrun

Mapeamento das rotas de graduação da UFSM: coleta dos currículos de todos os
cursos, modelagem em SQLite e (no fim) uma dashboard para descobrir a rota ótima
entre cursos, aproveitando cadeiras e equivalências.

## Estado

**Coleta completa** — 148 cursos, 528 versões, 12.313 ofertas, 8.297 disciplinas
(7.870 com ementa), 6.036 pré-requisitos, 5.008 equivalências. Validação:
6 ok · 3 atenção · 0 problemas.

- ✅ **Fases 0–5** — coleta, ETL e validação (`ufsm_speedrun/`)
- ✅ **Fase 7** — dashboard client-side em `web/` (ranking, plano, grafo, mapa)
- ⏳ **Fase 6** — equivalência heurística + otimizador de rota

Plano completo em [docs/plano.md](docs/plano.md), documentação da API do SIE em
[docs/ufsm-api.md](docs/ufsm-api.md) e o contrato de dados em
[docs/frontend-contrato.md](docs/frontend-contrato.md).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Uso

```powershell
# cria data/ufsm.db a partir do schema
.\.venv\Scripts\python.exe -m ufsm_speedrun init-db

# valida o pipeline com 1 request (e prova que o cache funciona)
.\.venv\Scripts\python.exe -m ufsm_speedrun smoke

# fases, em ordem (todas retomáveis: o cache evita refazer request)
.\.venv\Scripts\python.exe -m ufsm_speedrun discover
.\.venv\Scripts\python.exe -m ufsm_speedrun curriculos
.\.venv\Scripts\python.exe -m ufsm_speedrun relacoes
.\.venv\Scripts\python.exe -m ufsm_speedrun ementas

# ou o pipeline inteiro de uma vez
.\.venv\Scripts\python.exe -m ufsm_speedrun tudo

# o que já foi coletado
.\.venv\Scripts\python.exe -m ufsm_speedrun stats
```

## Como os dados são guardados

```
data/
├── raw/<endpoint>/<chave>.json   # envelope com request + response + hash
├── logs/requests.jsonl           # auditoria append-only (sem o corpo)
└── ufsm.db
```

Toda resposta é gravada antes de ser usada. O crawl acontece **uma vez**;
reprocessar o banco é só reler `data/raw/` — nunca refazer request.

## Política de acesso ao site da UFSM

1 request por vez, intervalo mínimo de 1,75 s (`--delay`), backoff exponencial,
`User-Agent` identificável e respeito ao `robots.txt`. Detalhes em
[docs/ufsm-api.md §12](docs/ufsm-api.md).
