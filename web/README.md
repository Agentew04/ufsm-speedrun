# ufsm/speedrun — dashboard (web/)

Dashboard **100% client-side**: abre o `data/ufsm.db` com `sql.js` (SQLite em
WebAssembly), monta o currículo dos 148 cursos em memória e calcula o custo de
fechar qualquer outro curso a partir do seu. Sem servidor, sem request para a
UFSM, sem telemetria — com o Wi-Fi desligado funciona igual.

## Rodar

```powershell
# 0. depois da coleta, gera os artefatos enxutos em data/public/
python -m ufsm_speedrun publicar

# 1. copia o núcleo publicado (data/public/ufsm-web.db + .gz) -> web/public/
python web/scripts/snapshot-db.py

# 2. dev server
cd web
npm install
npm run dev        # http://localhost:5173

# 3. build estático (dist/ serve em qualquer host, inclusive offline)
npm run build
```

Se o núcleo publicado não existir, o script copia `data/ufsm.db` completo
(51 MB). O front tenta `./ufsm.db.gz` (2,1 MB) e cai para `./ufsm.db`; os dois
funcionam no drag & drop. Ementas e bibliografias vêm em bancos separados e não
são usadas pelo otimizador.

Se `public/ufsm.db` não existir, a tela inicial pede o arquivo (arrastar e
soltar também funciona). Dá para apontar outro banco com `?db=./caminho.db`.

> **Não copie `data/ufsm.db` na mão.** A coleta usa WAL: os últimos commits
> ficam em `ufsm.db-wal`. O `snapshot-db.py` usa o backup API do SQLite e
> devolve um arquivo único consistente.

## O que tem

| aba | o que faz |
|---|---|
| **Ranking** | os 148 cursos ordenados por semestres extras, CH extra, cadeiras novas e % de reaproveitamento. Filtros por campus/modalidade. Currículos de ABI/núcleo comum (entrada, não diploma) ficam fora. |
| **Curso** | plano do curso-alvo: o que já vale, o que falta por período, cotas a preencher, timeline semestre a semestre (bin-packing com pré-requisitos) e grafo do currículo. |
| **Todos** | o run completo: rota gulosa para fechar os 148 cursos, custo marginal de cada passo, curva acumulada e os gargalos que servem mais currículos. |
| **Rede** | grafo bipartido curso ↔ disciplina mostrando as cadeiras compartilhadas (os "hubs" de reaproveitamento). |
| **Mapa** | heatmap 148×148: custo de ir de qualquer curso para qualquer curso. Clique abre o par. |
| **Método** | premissas, limites e estado da coleta. |

Clicar numa cadeira (na lista, no grafo ou nas alavancas) abre o **modal da
disciplina**: CH, créditos, departamento e a ementa. O texto vem de
`ementas.db.gz`, baixado só no primeiro clique; a **bibliografia** é um bloco
que baixa `bibliografias.db.gz` só quando você expande.

O toggle **"só meu campus (+ EaD)"** esconde cursos de outros campi e restringe
as cotas às disciplinas ofertadas no seu campus.

O checklist da barra lateral deixa ajustar o que já foi cumprido: semestre
atual, disciplinas individuais e cadeiras feitas em outro curso/instituição.
O interruptor **DCG estratégica** (só aparece quando o curso tem cota de DCG
aberta) decide se essas horas podem cobrir obrigatórias de outro curso.

## Como a conta é feita

Resumo (detalhes em [`docs/frontend.md`](../docs/frontend.md)):

- **disciplina é global** (`disciplina_id`), então cursar uma vez conta em todo
  currículo que a lista;
- **obrigatórias** do alvo que você não tem = cadeiras novas;
- **cotas** (`ch_minima` menos as obrigatórias do núcleo) precisam ser fechadas:
  - `DCG` com menu é **escolha**: itens do menu podem dispensar obrigatórias do
    alvo via equivalência (oficial/julgada/heurística), consumindo o orçamento
    de horas; cota aberta (1 das 129) aceita qualquer disciplina não-terminal;
  - `eletiva/optativa de núcleo` é menu fechado — só vale o que está listado;
  - **TCC/TCG, estágio e monografia nunca contam como DCG** (`eh_terminal`);
- **semestres extras** = bin-packing das cadeiras que faltam, respeitando
  pré-requisitos, período mínimo (`periodo_minimo`) e CH por estrutura
  (`requisito_ch`) e a CH máxima por período do curso-alvo;
- **equivalência efetiva** (`v_equivalencia_efetiva`: oficial + 943 pares
  julgados) credita a disciplina antiga no lugar da nova; `parcial` entra com
  badge mais fraco.

## Stack

- React 19 + TypeScript + Vite
- `sql.js` (SQLite/WASM) — leitura do banco no browser
- `cytoscape` — grafo do currículo e rede de reaproveitamento
- CSS próprio, sem framework; tema escuro; nenhuma fonte/asset externo

Tudo em `web/` é read-only sobre o banco. A coleta vive em `ufsm_speedrun/` e
não é tocada por aqui.
