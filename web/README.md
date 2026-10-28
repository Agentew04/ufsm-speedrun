# ufsm/speedrun — dashboard (web/)

Dashboard **100% client-side**: abre o `data/ufsm.db` com `sql.js` (SQLite em
WebAssembly), monta o currículo dos 148 cursos em memória e calcula o custo de
fechar qualquer outro curso a partir do seu. Sem servidor, sem request para a
UFSM, sem telemetria — com o Wi-Fi desligado funciona igual.

## Rodar

```powershell
# 1. copia o banco com o WAL já aplicado -> web/public/ufsm.db
python web/scripts/snapshot-db.py

# 2. dev server
cd web
npm install
npm run dev        # http://localhost:5173

# 3. build estático (dist/ serve em qualquer host, inclusive offline)
npm run build
```

Se `public/ufsm.db` não existir, a tela inicial pede o arquivo (arrastar e
soltar também funciona). Dá para apontar outro banco com `?db=./caminho.db`.

> **Não copie `data/ufsm.db` na mão.** A coleta usa WAL: os últimos commits
> ficam em `ufsm.db-wal`. O `snapshot-db.py` usa o backup API do SQLite e
> devolve um arquivo único consistente.

## O que tem

| aba | o que faz |
|---|---|
| **Ranking** | os 148 cursos ordenados por semestres extras, CH extra, cadeiras novas e % de reaproveitamento. Filtros por campus/modalidade. |
| **Curso** | plano do curso-alvo: o que já vale, o que falta por período, cotas a preencher, timeline semestre a semestre (bin-packing com pré-requisitos) e grafo do currículo. |
| **Rede** | grafo bipartido curso ↔ disciplina mostrando as cadeiras compartilhadas (os "hubs" de reaproveitamento). |
| **Mapa** | heatmap 148×148: custo de ir de qualquer curso para qualquer curso. Clique abre o par. |
| **Método** | premissas, limites e estado da coleta. |

O checklist da barra lateral deixa ajustar o que já foi cumprido: semestre
atual, disciplinas individuais e cadeiras feitas em outro curso/instituição.

## Como a conta é feita

Resumo (detalhes em [`docs/frontend.md`](../docs/frontend.md)):

- **disciplina é global** (`disciplina_id`), então cursar uma vez conta em todo
  currículo que a lista;
- **obrigatórias** do alvo que você não tem = cadeiras novas;
- **cotas** (`ch_minima` menos as obrigatórias do núcleo) precisam ser fechadas:
  - `DCG` e cota aberta aceitam qualquer disciplina — o que você já fez conta;
  - `eletiva/optativa de núcleo` é menu fechado — só vale o que está listado;
- **semestres extras** = bin-packing das cadeiras que faltam, respeitando os
  pré-requisitos catalogados e a CH máxima por período do curso-alvo;
- **equivalência oficial** (`equivalencia_item`) credita a disciplina antiga no
  lugar da nova, quando a coleta já trouxe o par.

## Stack

- React 19 + TypeScript + Vite
- `sql.js` (SQLite/WASM) — leitura do banco no browser
- `cytoscape` — grafo do currículo e rede de reaproveitamento
- CSS próprio, sem framework; tema escuro; nenhuma fonte/asset externo

Tudo em `web/` é read-only sobre o banco. A coleta vive em `ufsm_speedrun/` e
não é tocada por aqui.
