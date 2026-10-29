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

Hoje `web/src/db/load.ts:111` lê `equivalencia_bloco`/`equivalencia_item` — só o
que o SIE declara. A view nova entrega tudo já no formato `alvo → substituta`:

```sql
SELECT alvo_id, substituta_id, origem, confianca, veredito
FROM v_equivalencia_efetiva;
```

- `origem`: `oficial` | `julgada`
- `veredito`: `equivalente` | `parcial`

**Ganho medido no auditor**: incluindo as julgadas, a rota que fecha os 145
cursos cai de **5.144 → 4.981 disciplinas** e de **309.175 h → 301.180 h**
(−163 disciplinas, −7.995 h).

Estado atual: **943 pares julgados** (478 `equivalente`, 323 `parcial`,
142 `nao_equivalente`).

Sugestão de UI: badge `oficial` / `julgada (conf. 0,9)` no card da equivalência, e
tratar `parcial` como sinal mais fraco (não somar no `fixedEquiv` sem avisar).

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

## 6. Artefatos publicados (núcleo + ementas sob demanda)

`python -m ufsm_speedrun publicar` gera em `data/public/`:

| arquivo | tamanho | quando baixar |
|---|---|---|
| `ufsm-web.db.gz` | **2,1 MB** | no boot |
| `ementas.db.gz` | **4,1 MB** | no primeiro clique numa cadeira |
| `manifest.json` | — | metadados (tamanhos, contagens) |

O núcleo **não tem texto de ementa** (`programa_texto` é `NULL`) e não tem as
tabelas de ETL (`rota_*`, `ingest_run`). Do palpite heurístico sobraram só os
4.829 `equivalente` — a banda de revisão (19 MB) ficou de fora.

### Como carregar a ementa

```ts
import { inflate } from 'pako'   // ~45 KB

let ementas: SQL.Database | null = null

async function carregarEmentas() {
  if (ementas) return ementas
  const gz = await fetch('/ementas.db.gz').then(r => r.arrayBuffer())
  ementas = new SQL.Database(inflate(new Uint8Array(gz)))
  return ementas
}

async function ementaDe(disciplinaId: number) {
  const db = await carregarEmentas()
  const [res] = db.exec(
    'SELECT programa, objetivos_html, bibliografia FROM ementa WHERE disciplina_id = ?',
    [disciplinaId],
  )
  if (!res) return null
  const [programa, objetivos, bibliografia] = res.values[0]
  return { programa, objetivos, bibliografia }   // bibliografia pode ser null
}
```

Detalhes:
- carregue **uma vez** e guarde em memória (não re-baixe por clique)
- `bibliografia` só vem se publicarmos com `--com-bibliografia` (hoje vem `NULL`)
- o `ufsm-web.db` **não** tem esses campos — não tente `SELECT programa_texto` nele

### Atalho: não precisa de dois bancos no boot

Se preferir simplicidade, da para checar `manifest.json` e só habilitar o botão
"ver ementa" quando o arquivo existir. Mas os dois bancos são independentes:
quem nunca clicar nunca baixa os 4,1 MB.

## 7. Um detalhe de modelagem para vocês decidirem
`makeDone` + `scoreCourse` permitem que horas abertas do curso-base cubram
**qualquer** obrigatória do alvo (DCG estratégica). A regra é generosa — pela
contagem, `Música - Bacharelado` sai a 810 h de Ciência da Computação.

É a mesma regra dos dois lados, então não é divergência: é decisão de produto.
Se quiserem endurecer, o lugar é `scoreCourse` (`livre > 0 && fixedMissing`) e eu
acompanho no auditor. Vale no mínimo mostrar na UI que aquelas disciplinas foram
cobertas por cota, não cursadas.
