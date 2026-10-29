# Nota para a frente de frontend

> Escrito pela frente de dados em 2026-10-28. Três mudanças no banco e uma
> ferramenta nova. Nada aqui quebra o que já existe — é aditivo.

---

## 1. O banco mudou

Atualize a cópia (`data/ufsm.db` → `web/public/ufsm.db`) antes de testar.

| novidade | o que é |
|---|---|
| `curso.eh_nucleo_comum` + `curso.nucleo_comum_motivo` | classificação ABI calculada no ETL |
| **`v_equivalencia_efetiva`** (view) | equivalências oficiais **+ as 462 julgadas** |
| `equivalencia_julgada` | 233 `equivalente`, 193 `parcial`, 36 `nao_equivalente` |
| `rota_gulosa` / `rota_benchmark` | saída do auditor (Fase 6c) |

## 2. Trocar a origem das equivalências (maior ganho)

`web/src/db/load.ts:111` lê `equivalencia_bloco`/`equivalencia_item` — só o que o
SIE declara. A view entrega tudo já no formato `alvo → substituta`:

```sql
SELECT alvo_id, substituta_id, origem, confianca, veredito
FROM v_equivalencia_efetiva;
```

- `origem`: `oficial` | `julgada` | `heuristica` | `transitiva`
- `veredito`: `equivalente` | `parcial`

| origem | o que é | sugestão de UI |
|---|---|---|
| `oficial` | o SIE declara | selo normal |
| `julgada` | LLM revisou (943 pares) | selo "revisado" |
| `heuristica` | TF-IDF forte, nunca revisado | selo "sugestão (0,91)" |
| `transitiva` | fechamento de 2–3 saltos | selo "via <código>" |

### Duas regras que não são opcionais

**1. Nenhuma equivalência envolvendo disciplina terminal (TCC, estágio,
monografia) aparece na view.** TCC não se dispensa por equivalência nem por cota.
Antes dessa regra, a adjudicação gerou **415 pares TCC × TCC** (ementas genéricas,
tipo "elaborar o trabalho de conclusão") e eles estavam "cobrindo" TCCs na UI —
os TCCs sumiam de "cadeiras novas".

**2. Transitividade.** `python -m ufsm_speedrun fechar` fecha 2–3 saltos
(11.344 pares). O caso real:

```
ELC1086 METODOLOGIA DE PESQUISA EM INFORMÁTICA           (CC, código antigo)
ELC1077 METODOLOGIA DE PESQUISA EM SISTEMAS DE INFORMAÇÃO (CC, código novo)
UFSM01310 METODOLOGIA DE PESQUISA EM SISTEMAS DE INFORMAÇÃO (SI)

    ELC1086 ≡ ELC1077 (0,84)  ·  ELC1077 ≡ UFSM01310 (0,59)
    => ELC1086 ≡ UFSM01310  (transitiva, 0,59)
```

Sem fechamento, quem fez a disciplina antiga não "vê" a nova.

**Ganho medido no auditor**: a rota que fecha os 145 cursos cai de
**5.144 → 4.192 disciplinas** e de **309.175 → 258.760 h**.

Estado: 25.322 pares na view (4.707 oficiais, 1.314 julgadas, 7.957 heurísticas,
11.344 transitivas).

## 3. Classificação de ABI saiu da UI

`load.ts:247` recalcula a cada carregamento:

```ts
const ehNucleoComum = (nome, lista, chTotal) => { ... }
```

A regra foi portada para o ETL e virou coluna. Basta ler:

```sql
SELECT id, eh_nucleo_comum, nucleo_comum_motivo FROM curso;
```

Valores atuais (2 cursos):

```
960 h   Artes Cênicas - Bacharelado           — ABI: irmão com 2756 h (2.9×)
1080 h  Ciências Biológicas - Núcleo Comum    — nome contém 'núcleo comum'
```

A regra do TS dá exatamente o mesmo resultado hoje — então a troca é segura. Vale
manter o fallback por uma versão e depois remover.

## 4. Auditor: como comparar as duas implementações

O otimizador de produção é o de vocês. Eu escrevi uma segunda implementação
independente (`ufsm_speedrun/auditor.py`) que roda sobre o mesmo banco. Duas
implementações se vigiando é o que pega regra que mudou de um lado só.

```powershell
python -m ufsm_speedrun auditar
# -> data/exports/auditoria-rota.json
```

Para comparar, exporte do front um JSON neste formato:

```json
{
  "base_curso_id": 701,
  "passos":     [{"ordem": 1, "curso_id": 1250, "horasPasso": 900}],
  "benchmark":  [{"alvo_curso_id": 1250, "horas": 900, "disciplinas": 16, "semestres": 2}]
}
```

e rode:

```powershell
python -m ufsm_speedrun auditar --front caminho/para/front.json
```

Saída: nº de divergências + até 20 exemplos. **Zero divergência = as duas
implementações concordam naquele cenário.**

O `passos` é o objeto de `buildSpeedrun`; o `benchmark` é o resultado de
`scoreCourse` para cada alvo. Um botão "exportar diagnóstico" no modo dev resolve.

## 5. DCG: menu fechado e disciplinas terminais
O modelo atual trata toda cota de DCG como "qualquer disciplina". Os dados dizem
que isso é exceção: **129 cotas, 128 com menu listado, 1 aberta** (SI/2026, 420 h).

Nova tabela **`dcg_elegivel`** (`curso_id, estrutura_id, disciplina_id, fonte,
horas_cota`), materializada por `python -m ufsm_speedrun dcg`:

```sql
SELECT disciplina_id FROM dcg_elegivel
WHERE curso_id = ? AND estrutura_id = ? AND fonte = 'menu';
```

- `fonte = 'menu'` → a lista explícita do currículo
- `fonte = 'aberta'` → cota sem lista; a tabela já traz o que é elegível

E a exceção de domínio: **`disciplina.eh_terminal`** marca TCC/TCG/TG, estágio e
monografia (**594** no catálogo). Nenhuma delas aparece em `dcg_elegivel`.

Isso corrige duas coisas:

1. **"TCC de SI como DCG de CC" deixa de existir** — o menu do CC tem 57
   disciplinas e nenhuma é TCC.
2. As obrigatórias terminais do curso-alvo não podem ser "cobertas" por horas de
   DCG do curso-base (`fixedDcg`). TCC não se dispensa por cota — você faz o TCC
   do curso que vai receber o diploma.

Impacto medido no auditor: rota **4.991 → 5.152 disciplinas**, 301.480 → 311.260 h.

Se for implementar só uma coisa desta lista, é essa.

### O menu é escolha estratégica, não só cota

Fechar o menu resolveu o abuso ("TCC de SI como DCG de CC"), mas derrubou um caso
legítimo — e a causa não era a restrição:

> `ELC1070 GERÊNCIA DE PROJETOS DE SOFTWARE` é DCG do CC.
> `UFSM01299 GERÊNCIA DE PROJETOS` é **obrigatória** do SI.
> O SIE declara oficialmente que uma dispensa a outra (`SI ← CC`, direção certa).

O problema é que **o modelo nunca "cursa" itens do menu** — ele trata a cota como
horas a preencher. Assim a equivalência existia no banco, mas `done.ids` nunca
continha `ELC1070`, e nada acontecia.

Antes da restrição isso "funcionava" pelo motivo errado: a cota aberta era um
curinga que cobria qualquer obrigatória.

**Correção:** a cota de DCG com menu vira um conjunto de **escolhas** que o solver
faz para maximizar valor no curso-alvo.

```ts
// em makeDone(base): guarde o menu e o orçamento
done.menu = new Map<number, number>()   // discId -> CH
done.menuHoras = 0
for (const q of base.quotas) {
  if (q.kind !== 'dcg' || !q.candidatos.length) continue
  done.menuHoras += q.horas
  for (const d of q.candidatos) done.menu.set(d, chDe(universo, d))
}

// em scoreCourse(target): cubra obrigatórias cujo substituto está no menu
let orcamento = done.menuHoras
for (const o of faltantesOrdenadasPorCH) {
  const subs = new Set([o.discId, ...(target.equivals.get(o.discId) ?? []).map(e => e.discId)])
  const escolha = [...done.menu.keys()]
    .filter(m => subs.has(m) && done.menu.get(m)! <= orcamento)
    .sort((a, b) => done.menu.get(a)! - done.menu.get(b)!)[0]
  if (escolha === undefined) continue
  orcamento -= done.menu.get(escolha)!
  cobrir(o, escolha)      // entra em fixedDcg, consumindo o orçamento
}
```

Resultado medido (base CC → alvo SI):

| | antes | agora |
|---|---|---|
| obrigatórias faltando | 21 | **8** |
| semestres estimados | 3 | **1** |
| dispensadas por DCG | 0 | **8** |

E as escolhas são exatamente as esperadas:

```
CAD1002 TEORIA GERAL DA ADMINISTRAÇÃO   -> CAD1137 ORGANIZAÇÃO E ADMINISTRAÇÃO
CIE1002 TEORIA ECONÔMICA                -> UFSM01309 INTRODUÇÃO À ECONOMIA
ELC1070 GERÊNCIA DE PROJETOS DE SOFTWARE -> UFSM01299 GERÊNCIA DE PROJETOS
ELC1072 INTERFACE HUMANO-COMPUTADOR      -> UFSM01297 INTERAÇÃO HUMANO-COMPUTADOR
```

> ⚠️ O `orcamento` é consumido: uma vez escolhido `ELC1070` para o SI, aquelas
> 60 h não estão mais disponíveis para outro alvo. No guloso, isso precisa ser
> estado mutável entre passos (como já é `livreAberto`).

### E a heurística agora conta

`v_equivalencia_efetiva` passou a incluir os pares `veredito = 'equivalente'` da
heurística (4.829 pares, 8.435 direções) com `origem = 'heuristica'` e
`confianca = score_final`. Antes eles ficavam invisíveis: nunca foram julgados e
não entravam na view.

Sugestão de UI: `oficial` e `julgada` com selo normal; `heuristica` com selo
"sugestão (0,91)" — é palpite de texto, não decisão de colegiado.

## 6. Requisitos de período e de carga horária

O SIE registra dois tipos de condição que o plano semestral ignorava:

| tipo | o que exige | onde está agora |
|---|---|---|
| 5 — período vencido | ter vencido o período N | `disciplina_curriculo.periodo_minimo = N` |
| 3 — CH numa estrutura | ter H horas na estrutura X | tabela `requisito_ch` |

Rodar `python -m ufsm_speedrun requisitos` materializa os dois.

### Período vencido (o mais comum: 301 ofertas)

```sql
SELECT periodo_minimo FROM disciplina_curriculo WHERE id = ?;
-- se N não for nulo, a disciplina só pode entrar a partir do período N+1
```

No `earliest()` de `plan.ts`, é um `max` a mais:

```ts
const pm = Number(row.periodo_minimo ?? 0)
if (pm > 0) resultado = Math.max(resultado, pm + 1)
```

### Carga horária em estrutura (62 ofertas)

Uma linha por estrutura exigida. **`estrutura_id` nulo significa "GERAL"** —
total do curso, que aceita somatório de qualquer estrutura:

```sql
SELECT estrutura_id, horas FROM requisito_ch WHERE disciplina_curriculo_id = ?;
```

Regra: para cada linha, a CH cumprida **naquela estrutura** precisa ser ≥ `horas`;
quando `estrutura_id` é nulo, vale a CH total do curso.

### Créditos vencidos (tipo 4)

Zero ocorrências no banco — não precisa implementar. Se aparecer, é dado novo.

> Impacto: sem isso, a agenda colocava disciplina no 1º semestre que exige ter
> vencido o 5º. Não muda o custo total, mas muda a ordem — e a ordem é o produto.

## 7. Artefatos publicados: três bancos, três momentos

`python -m ufsm_speedrun publicar` gera em `data/public/`. Cada arquivo existe
porque corresponde a uma affordance diferente da UI — nada baixa antes da hora.

| arquivo | tamanho | quando baixar |
|---|---|---|
| `ufsm-web.db.gz` | **2,1 MB** | no boot |
| `ementas.db.gz` | **4,1 MB** | ao abrir a cadeira (programa + objetivos) |
| `bibliografias.db.gz` | **4,2 MB** | ao expandir o bloco "Bibliografia" |
| `manifest.json` | — | metadados (tamanhos, contagens, momento de carga) |

O núcleo **não tem texto** (`programa_texto`, `bibliografia_texto`,
`objetivos_html` são `NULL`) e não tem as tabelas de ETL (`rota_*`,
`ingest_run`). Do palpite heurístico sobraram só os 4.829 `equivalente` — a
banda de revisão (19 MB) ficou de fora.

> ⚠️ A coluna `ementa.bibliografia` **existe mas vem sempre `NULL`**, reservada
> para compatibilidade. A bibliografia real está em `bibliografias.db`.

### Carregamento sob demanda

```ts
import { inflate } from 'pako'   // ~45 KB

const cache = new Map<string, SQL.Database>()

async function banco(nome: 'ementas' | 'bibliografias'): Promise<SQL.Database> {
  const pronto = cache.get(nome)
  if (pronto) return pronto
  const gz = await fetch(`/${nome}.db.gz`).then(r => r.arrayBuffer())
  const db = new SQL.Database(inflate(new Uint8Array(gz)))
  cache.set(nome, db)
  return db
}

// 1) ao abrir a cadeira
async function ementaDe(id: number) {
  const db = await banco('ementas')
  const [res] = db.exec('SELECT programa, objetivos_html FROM ementa WHERE disciplina_id = ?', [id])
  return res ? { programa: res.values[0][0], objetivos: res.values[0][1] } : null
}

// 2) ao expandir o bloco de bibliografia (dropdown)
async function bibliografiaDe(id: number) {
  const db = await banco('bibliografias')
  const [res] = db.exec('SELECT texto FROM bibliografia WHERE disciplina_id = ?', [id])
  return res ? res.values[0][0] : null
}
```

Detalhes que importam:

- carregue **uma vez por sessão** e guarde no `cache` (não re-baixe por clique)
- o dropdown mostra "carregando…" no primeiro expandir e depois fica instantâneo
- quem só lê a ementa nunca baixa `bibliografias.db`
- o `ufsm-web.db` **não** tem esses campos: não tente `SELECT programa_texto` nele

### Se 4,2 MB no expandir incomodar

Dá para fatiar `bibliografias.db` por prefixo de código (`bib-ELC.db.gz`,
`bib-MTM.db.gz`, ~60 arquivos de ~70 KB) e buscar só o do prefixo da disciplina.
O build sabe o prefixo, então é barato de fazer depois — mas multiplica arquivos
e caches. Hoje não vale; só se o uso mostrar que muita gente expande bibliografia.

## 8. Um detalhe de modelagem para vocês decidirem
`makeDone` + `scoreCourse` permitem que horas abertas do curso-base cubram
**qualquer** obrigatória do alvo (DCG estratégica). A regra é generosa — pela
contagem, `Música - Bacharelado` sai a 810 h de Ciência da Computação.

É a mesma regra dos dois lados, então não é divergência: é decisão de produto.
Se quiserem endurecer, o lugar é `scoreCourse` (`livre > 0 && fixedMissing`) e eu
acompanho no auditor. Vale no mínimo mostrar na UI que aquelas disciplinas foram
cobertas por cota, não cursadas.
