# Otimizador de rota — estado atual e divisão de responsabilidades

> Leitura read-only do `web/` em 2026-10-28. Objetivo: decidir o que a frente de
> dados (Python) deve fazer na Fase 6c sem duplicar o que já existe.

---

## 1. Veredito curto

**O otimizador já existe e está no front, e está bem feito.** Não devo escrever um
segundo otimizador em Python. O que falta é dados que o front ainda não consome.

## 2. Inventário do que já existe

| peça | onde | o que faz |
|---|---|---|
| `scoreCourse` | `web/src/lib/plan.ts:143` | custo marginal de fechar um curso: obrigatórias, equivalências oficiais, DCG estratégica, cotas de eletiva/DCG/livre |
| `planSemesters` | `web/src/lib/plan.ts:332` | aloca as faltantes em semestres respeitando pré-requisitos (OR de blocos, AND dentro) e teto de CH |
| `buildSpeedrun` | `web/src/lib/speedrun.ts:155` | guloso: a cada passo fecha o curso de menor custo marginal dado o pool |
| `buildMatrix` | `web/src/lib/plan.ts:417` | matriz 148×148 base × alvo |
| `leverInsights` | `web/src/lib/plan.ts:444` | disciplinas que destravam mais cursos |
| `ehNucleoComum` | `web/src/db/load.ts:247` | marca ABI/núcleo comum |

Conceitos que já estão corretos lá e que eu não preciso reinventar:
- **DCG estratégica**: horas de cota aberta do curso-base podem cobrir obrigatórias
  do alvo ("fiz SI de graça como DCG do CC"). `speedrun.ts:84-100`.
- **Equivalência oficial** cobrindo obrigatória não cursada. `plan.ts:158`.
- **Cota fechada vs aberta**: menu de eletiva não aceita qualquer disciplina;
  DCG/livre aceita. `plan.ts:105-107`.
- **Guloso é ordem-dependente no caminho, não no total** — e eles documentam isso.

## 3. Onde estaria o conflito

Se eu implementar a Fase 6c em Python como "o otimizador", passam a existir duas
implementações da mesma regra de negócio. Elas vão divergir no primeiro ajuste de
critério (é sempre assim), e aí ninguém sabe qual número é o verdadeiro.

### Fronteira proposta

| responsabilidade | dono | por quê |
|---|---|---|
| coleta, ETL, validação | **Python** | já é |
| equivalência heurística + julgamento | **Python** | precisa de TF-IDF, texto, LLM |
| classificação do curso (ABI/núcleo comum) | **Python** (hoje é TS) | é propriedade do **dado**, não da tela |
| score interativo ("e se eu fizer X?") | **TS** | precisa ser instantâneo |
| agenda semestral, matriz, grafo | **TS** | idem |
| **auditoria/benchmark do guloso** | **Python** | offline, roda 1×, não precisa de browser |

Regra de bolso: **se depende de texto/LLM ou é propriedade permanente do dado,
é Python; se depende da escolha do usuário naquele segundo, é TS.**

## 4. O que falta de verdade (ganho real, sem duplicar)

### 4.1 As equivalências julgadas não são usadas — maior ganho
`web/src/db/load.ts:111` lê apenas `equivalencia_bloco`/`equivalencia_item`
(declaradas pelo SIE). As **233 equivalentes confirmadas** + 193 parciais estão em
`equivalencia_julgada` e não chegam na tela.

Impacto: cursos ficam com custo maior do que realmente têm. Pares
presencial × EaD (ex.: `LTC1004 LATIM BÁSICO` ↔ `EAD1095 LATIM BÁSICO - EAD`)
não contam como aproveitamento.

Custo de implementar: uma query a mais no load + merge no mapa `equivals`, com
flag de origem (`oficial` | `julgada`) para dar transparência.

### 4.2 `nucleo_comum` deveria vir do banco
Hoje `load.ts:247` recalcula a cada carregamento:

```
é ABI se: nome contém "núcleo comum"
       ou: irmão com mesmo nome_lista tem >= 2x a CH e este tem < 2000h
```

Medi a regra no banco: marca **exatamente 2** cursos —
`Artes Cênicas - Bacharelado` (960 h, irmão de 2.756 h) e
`Ciências Biológicas - Núcleo Comum` (1.080 h, irmão de 3.985 h).
Os 2 tecnólogos de 1.630 h e 1.970 h **não** são marcados, corretamente
(são cursos completos de 3 anos).

A regra está certa — o problema é o lugar. Se a heurística mudar, Python e TS
divergem. Proposta: coluna `curso.eh_nucleo_comum` + `motivo`, preenchida no ETL.

### 4.3 Campus não entra na rota
Disciplina ofertada em Cachoeira do Sul não é cursável por quem está em Santa
Maria. O grafo hoje trata tudo como um campus só. Afeta 30 cursos (11 EaD, 7 FW,
7 Palmeira, 6 Cachoeira).

### 4.4 Pré-requisitos tipos 3/4/5 são ignorados
`plan.ts:135` ignora tudo que não é tipo 1/2, deliberadamente ("sinal fraco").
No banco são **1.308 itens de "período vencido"** (31% do total de pré-requisitos)
e 79 de "CH vencida". A decisão é defensável, mas o usuário deveria saber que a
agenda não as considera.

### 4.5 Sem oferta por semestre
Não há dado de turmas/horários no SIE web. A agenda é teórica. Fora de escopo.

## 5. Se ainda quisermos código Python na Fase 6c

Escopo honesto: **auditor, não segundo produto**.

1. Reimplementar o mesmo guloso sobre o banco (SQL + Python puro).
2. Comparar com os números do front → **detecta divergência de regra** entre as
   duas implementações (foi assim que o bug das 5.008 equivalências apareceu).
3. Rodar uma busca melhor (troca local / ILP pequeno com OR-Tools) e responder:
   *"o guloso está a quantos % do ótimo?"*.
4. Gravar `rota_benchmark` (rota, custo, tempo, gap) como teste de regressão.

O que **não** fazer: UI, agenda interativa, segundo grafo.

## 6. Ordem recomendada

1. **Front consumir `equivalencia_julgada`** — 1 query, maior impacto; não toca
   em nenhuma regra existente.
2. **`eh_nucleo_comum` no banco** — remove duplicação Python/TS.
3. **Auditor do guloso** — rede de segurança quando coleta ou equivalência mudar.
4. **Campus na rota** — só se o produto for usar isso de verdade.

## 7. Implementado (2026-10-28)

| item | estado |
|---|---|
| `v_equivalencia_efetiva` (oficial + julgadas) | ✅ criada |
| `curso.eh_nucleo_comum` + motivo | ✅ 2 cursos classificados |
| auditor `ufsm_speedrun/auditor.py` | ✅ roda e grava `rota_gulosa` + `rota_benchmark` |
| `auditar --front arquivo.json` | ✅ compara as duas implementações |
| nota para o frontend | ✅ `docs/nota-frontend.md` |

Comandos:

```powershell
python -m ufsm_speedrun classificar   # marca ABI/núcleo comum
python -m ufsm_speedrun auditar       # rota + benchmark + JSON
python -m ufsm_speedrun auditar --front data/exports/front.json
```

### Impacto das equivalências julgadas

Rota que fecha os 145 cursos (base = Ciência da Computação):

| equivalências | disciplinas | horas |
|---|---|---|
| só oficiais | 5.144 | 309.175 |
| **oficiais + julgadas** | **4.991** | **301.480** |

**−153 disciplinas e −7.695 h** — é o argumento para o front passar a ler a view.

### Custo/benefício do auditor

- benchmark 148 × 147 + guloso completo: ~1 min de CPU
- roda offline, 1× por mudança de coleta ou de regra
- serve de teste de regressão: se a coleta mudar, os números mudam e a divergência
  aparece antes de chegar no usuário

## 8. Política de DCG (menu fechado vs cota aberta)

O modelo atual trata toda cota de DCG como **"qualquer disciplina do catálogo"**.
Os dados dizem que isso é exceção, não regra:

| situação | quantidade |
|---|---|
| estruturas de DCG **com menu listado** | **129** |
| cotas realmente abertas (sem disciplinas, sem atividades) | 21 (só 2 são DCG) |

O DCG de Ciência da Computação/2024, por exemplo, é um menu de **57 disciplinas**
— 38 dos departamentos de computação, 4 de administração, 3 de física, 3 de
letras, 2 de educação. Música não está lá.

Ou seja: **respeitar o menu resolve o caso real**. A heurística de "mesma área"
seria pior que o menu — excluiria as 4 disciplinas de Administração aprovadas e
não impediria nada que o menu já não impeça.

### Impacto medido

| política | disciplinas na rota | horas |
|---|---|---|
| `aberta` (curinga) | 4.192 | 258.760 |
| `menu` (fechado + escolha estratégica) | **4.353** | **267.625** |

O menu fechado custa **+161 disciplinas** em relação ao curinga — é o preço de não
poder inventar. Mas o número absoluto caiu muito nos dois lados depois do
fechamento transitivo das equivalências e da exclusão de terminais.

O que **não** pode faltar junto com o menu é a escolha estratégica (ver
`docs/nota-frontend.md §5`): sem ela, fechar o menu derruba o aproveitamento de
DCG entre cursos a zero.

### Implementado

Tabela **`dcg_elegivel`** materializada (`python -m ufsm_speedrun dcg`):

```
129 cotas de DCG · 15.209 pares
  128 com menu listado (4.657 pares)
    1 cota aberta (SI/2026, 420 h)
```

Regra: se a estrutura tem menu, só o menu vale; se não tem, qualquer disciplina
não-terminal e ativa. Nunca as duas coisas ao mesmo tempo.

E a exceção de domínio que o usuário apontou: **disciplinas terminais**
(TCC/TCG/TG, estágio, monografia) **nunca** entram numa cota de DCG — nem no menu.
São 594 no catálogo; 21 entradas de menu foram barradas. O TCC de SI como DCG de
CC deixa de existir, e o TCC volta a ser obrigação de verdade.

```powershell
python -m ufsm_speedrun classificar   # cursos ABI + disciplinas terminais
python -m ufsm_speedrun dcg           # materializa a elegibilidade
python -m ufsm_speedrun auditar --dcg menu
```


Para as ~2 cotas de DCG realmente abertas (SI/2026: 420 h sem lista), aí sim cabe
uma regra de área — mas como sugestão explícita, nunca como default silencioso.

## 9. Campus e requisitos de período (P1)

### Campus

`auditar --campus mesmo` filtra os alvos para o campus-base + EaD e restringe as
disciplinas elegíveis às ofertadas ali. Base CC/Santa Maria:

| política | cursos | disciplinas | horas |
|---|---|---|---|
| `livre` (atual do front) | 145 | 5.152 | 311.260 |
| **`mesmo`** | **125** | **4.237** | **256.040** |

Os 20 cursos restantes ficam em Cachoeira do Sul, Frederico Westphalen, Palmeira
das Missões ou fora do EaD elegível. `curso.campus` vem do SIE; **2.017
disciplinas não têm oferta em Santa Maria**.

### Requisitos de período e CH

`python -m ufsm_speedrun requisitos` materializa:

```
período vencido (tipo 5) .... 301 ofertas  -> periodo_minimo
CH em estrutura (tipo 3) ....  79 exigências em 62 ofertas -> requisito_ch
créditos vencidos (tipo 4) ...   0 itens (não existe no banco)
```

Regra para o cliente: `periodo_minimo = N` significa "só a partir do período N+1";
`requisito_ch.estrutura_id` nulo significa "GERAL" (total do curso). Detalhes em
`docs/nota-frontend.md §6`.

## 10. Números para calibrar

```
cursos ........................ 148  (2 são ABI/núcleo comum)
ofertas de disciplina ......... 12.313
ofertas com relação ........... 6.031
arestas de pré-requisito ...... 4.649   (1.308 período vencido + 79 CH, agora materializados)
equivalências oficiais ........ 3.862 pares
equivalências julgadas ........ 478 equivalente · 323 parcial · 142 não
cotas de DCG elegíveis ........ 129 (128 menu + 1 aberta) · 15.209 pares
disciplinas terminais ......... 594 (TCC/estágio/monografia)
```
