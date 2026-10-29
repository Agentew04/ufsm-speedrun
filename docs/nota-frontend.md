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
cursos cai de **5.144 → 4.991 disciplinas** e de **309.175 h → 301.480 h**
(−153 disciplinas, −7.695 h).

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

## 5. Um detalhe de modelagem para vocês decidirem

`makeDone` + `scoreCourse` permitem que horas abertas do curso-base cubram
**qualquer** obrigatória do alvo (DCG estratégica). A regra é generosa — pela
contagem, `Música - Bacharelado` sai a 810 h de Ciência da Computação.

É a mesma regra dos dois lados, então não é divergência: é decisão de produto.
Se quiserem endurecer, o lugar é `scoreCourse` (`livre > 0 && fixedMissing`) e eu
acompanho no auditor. Vale no mínimo mostrar na UI que aquelas disciplinas foram
cobertas por cota, não cursadas.
