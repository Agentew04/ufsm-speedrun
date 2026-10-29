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
com um servidor estático local). O front baixa o **núcleo publicado**
(`data/public/ufsm-web.db.gz`, 2,1 MB) e descomprime no browser
(`DecompressionStream`); o `.db` completo (51 MB) fica como fallback de
desenvolvimento. Ementas e bibliografias vivem em bancos separados
(`ementas.db`, `bibliografias.db`) e não entram no otimizador.

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
5. **DCG é menu fechado** (128 das 129 cotas): a lista vem de `dcg_elegivel`
   (materializada por `python -m ufsm_speedrun dcg`), não de "qualquer
   disciplina". Só a cota aberta aceita o catálogo. Uma cota com menu **não é
   hora livre**: serve para a própria cota, nunca para cobrir obrigatória de
   outro curso.
6. **Disciplinas terminais** (`eh_terminal = 1`: TCC/TCG/TG, estágio,
   monografia — 594 no catálogo) **nunca** entram como DCG, nem por menu, nem
   como cobertura de cota. TCC é do curso que dá o diploma.
7. **ABI/núcleo comum**: alguns `curso` são só a entrada (Artes Cênicas
   "Bacharelado" = 960 h; o grau sai em Direção/Interpretação, 2.756 h). A flag
   `Curso.nucleoComum` (coluna `eh_nucleo_comum` do ETL, com fallback) os tira do
   ranking/matriz/run e mostra um aviso quando são o curso-base.
8. **Núcleo sem `ch_minima`**: se a soma dos núcleos não fecha com
   `versao.ch_total`, a diferença entra como cota residual ("horas fora dos
   núcleos mapeados"). Sem isso, Música/Bacharelado parecia 1.110 h mais barata.

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

**DCG:** menu fechado (128 das 129 cotas) — `dcg_elegivel` diz o que pode
preencher cada cota, já sem as disciplinas terminais. Uma cota com menu **não é
hora livre**: só preenche a própria cota. A cota aberta (ex.: SI/2026) aceita
qualquer disciplina não-terminal, e só ela pode ser "estratégica":

```
livre = horas de DCG em cota ABERTA do curso-base
para cada obrigatória do alvo que falta, da maior CH para a menor:
    se não é terminal, cabe em livre e os pré-requisitos estão satisfeitos:
        conta como cumprida (badge DCG) e livre -= CH
o resto de livre + as disciplinas do aluno fora do alvo formam o pool das cotas
```

Menu fechado (`dcg` com lista) e `eletiva` de núcleo **não** entram nessa conta:
só vale a lista. Como o CC tem DCG em menu, ele não tem horas estratégicas — a
UI mostra "menu fechado de 57 disciplinas" em vez do interruptor.

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
| pré-requisitos ~25% das ofertas (100% das que declaram) | plano semestral otimista | nada no front; depende da Fase 3 |
| equivalências | resolvido em 2026-10-28 (5.003 pares) | manter de olho na reingestão |
| ementas 79% preenchidas | nenhum (ainda não usadas) | Fase 6a + badge na UI |
| reformas trocam códigos | queda brusca de sobreposição (ex.: CC/2026) | equivalência oficial já cobre parte |
| ABI/núcleo comum | ranking mentia (Artes Cênicas 960 h) | marcados e excluídos do ranking (§8.2) |
| núcleo flexível sem cota | curso parecia mais barato | cota residual contra `ch_total` (§8.3) |
| DCG tratada como "qualquer disciplina" | TCC/música contavam em qualquer curso | menu `dcg_elegivel` + terminais (§8.5) |
| oferta de turma/horário não modelada | semestres otimistas | integrar horários (não existe no SIE público) |
| cota restrita usa só o menu do núcleo | pode subestimar equivalência aprovada caso a caso | revisão humana da Fase 6a |

O front é **tolerante a dado parcial**: `LEFT JOIN` em tudo, estados vazios
explícitos ("a coleta ainda não chegou neste curso"), e o topo mostra a
porcentagem de ofertas com pré-requisito. Reexportar o banco melhora os números
sem mexer no código.

## 7. Run completo (aba `Todos`)

Pergunta: "e para fazer **todos** os outros?". `lib/speedrun.ts` monta a rota.

- **Pool** = tudo que o aluno já tem (`done.ids` + horas de eletiva).
- **Custo marginal** de um curso = as mesmas regras do §3, mas com o pool no
  lugar de `done`: obrigatórias que faltam, equivalências efetivas, cotas de
  DCG menu fechado preenchidas pelas candidatas do menu e cotas abertas pelo
  excedente do pool.
- A **DCG estratégica** do curso-base só existe se ele tiver cota de DCG aberta
  (o CC não tem: o menu de 57 disciplinas não é hora livre).
- **Rota gulosa**: a cada passo escolhe o curso de menor custo marginal
  (horas, depois nº de cadeiras). O curso escolhido fecha; os que já estavam
  cobertos entram como passos de 0 h.
- As cadeiras novas do passo entram no pool — é isso que faz os cursos
  seguintes ficarem mais baratos.

Fatos que a tela deixa explícitos:

- **O total não depende da ordem** (união de conjuntos). A ordem muda só *quando*
  cada curso fecha; a rota gulosa minimiza cada passo.
- Com Ciência da Computação como base (banco de 2026-10-28, DCG em menu):
  **5.117 cadeiras distintas**, **312.610 h** extras, **~579 semestres
  (~290 anos)** — 4.154 cadeiras pertencem a um único currículo e 718 aparecem
  em 2+ cursos. Metade das horas está nos primeiros 94 cursos; a cauda é
  Medicina/Veterinária/Agronomia.
- A curva (barras = custo do passo, linha = acumulado) mostra o "degrau" que
  cada curso caro impõe.

Limites: o run inteiro não simula pré-requisitos (seria uma árvore de 5 mil
nós); o semestre de fechamento é `CH acumulada ÷ carga média`. Cada passo
individual continua tendo o plano completo na aba **Curso**.

## 8. Qualidade de dados: equivalências, ABI e núcleos sem cota

### 8.1 Equivalências (resolvido na coleta)

O parser de `ufsm_speedrun/relacoes.py` lia `item["disciplinaRequisito"]` (campo
de pré-requisito) e gravava `equivalencia_item` sem a disciplina de origem. Foi
corrigido na frente A e o banco reexportado em 2026-10-28: **5.003 pares** com
id/código (antes: 0). Efeito medido em CC→SI: 3 semestres/1.470 h → **2
semestres/900 h/62% de reaproveitamento**, exatamente o caso "terminei CC e no
semestre seguinte fechei SI". O `prereq_*` sempre esteve certo (3.071/3.101).

### 8.2 ABI / núcleo comum

`curso.nome_lista` agrupa o ABI; alguns registros são só a **entrada**:

| id | curso | CH | semestres | irmãos |
|---|---|---|---|---|
| 837 | Artes Cênicas - Bacharelado | 960 | 3 | Direção/Interpretação Teatral, 2.756 h |
| 686 | Ciências Biológicas - Núcleo Comum | 1.080 | 3 | Bacharelado 3.535 h / Licenciatura 3.985 h |

Sem isso, o ranking dizia que "fechar Artes Cênicas" custava 480 h. Agora
`Curso.nucleoComum` marca os dois e eles **saem do ranking/matriz/run** (podem
ser escolhidos como curso de origem, com aviso na UI). Critério: nome contém
"núcleo comum" ou `ch_total < 2 ×` o maior irmão do mesmo `nome_lista`.

### 8.3 Núcleo flexível sem `ch_minima`

11 cursos tinham mais horas em `ch_total` do que a soma dos núcleos declarados
— ex.: **Música - Bacharelado (1.001)**: 2.400 h declaradas, 1.290 h mapeadas
(o nó "DCG" tem 34 ofertas e `ch_minima = NULL`). A diferença agora entra como
cota residual ("horas do currículo fora dos núcleos mapeados"), preenchida por
qualquer disciplina. Números: Música 1.110 h, Sociologia EaD 960 h, Artes
Visuais/Licenciatura 795 h, CC 330 h, Eng. Telecom 390 h.

### 8.4 Ementas e CH nula

11.159 de 11.159 disciplinas com `programa_texto` (100%) — o `.db` está em 51 MB,
ainda tranquilo para o sql.js. Duas disciplinas vêm com `ch_total = NULL`
(`QMC1885`, `QMC1886`) e entram com 0 h; vale um aviso para a coleta.

### 8.5 DCG: menu fechado e disciplinas terminais

Até 2026-10-28 o front tratava toda cota de DCG como "qualquer disciplina".
Os dados mostram o contrário: **129 cotas, 128 com menu listado e 1 aberta**
(SI/2026). O ETL materializa em `dcg_elegivel`:

- `fonte='menu'` → as disciplinas listadas no currículo (4.657 linhas);
- `fonte='aberta'` → catálogo não-terminal (10.552 linhas, só a cota do SI).

E **594 disciplinas `eh_terminal`** (TCC/TCG/TG, estágio, monografia) nunca
entram — nem no menu, nem como cobertura por cota.

No front:

- cota de DCG com menu só é preenchida por disciplina **do menu** (o excedente do
  pool não serve);
- cota de DCG com menu **não é hora livre**: não cobre obrigatória de outro
  curso. Só a cota aberta pode (com pré-requisito satisfeito e sem terminal);
- TCC/estágio do curso-alvo **nunca** é coberto por DCG.

Efeito: CC→SI volta de 2 para **3 semestres / 1.320 h** (só 1 obrigatória do SI
está no menu de 57 do CC), e o run vai para 5.117 cadeiras / 312.610 h. O
"TCC de SI como DCG de CC" deixa de existir.

## 9. Auditoria cruzada (frente A × frente B)

O auditor em `ufsm_speedrun/auditor.py` é uma segunda implementação das mesmas
regras. Para comparar, o front exporta o JSON no formato dele:

- aba **Todos** → botão "exportar diagnóstico"; ou
- modo dev `?diag=1#b=701` (renderiza o JSON puro na página).

```
python web/scripts/snapshot-db.py
python -m ufsm_speedrun auditar                 # referência
python -m ufsm_speedrun auditar --front front-diag-701.json
```

Resultado em 2026-10-28 (base CC, 146 alvos, `--dcg menu`):

| | python | front |
|---|---|---|
| benchmark (custo por alvo) | — | **0 divergências em 146** |
| rota | 145 cursos · 5.152 disc · 311.260 h | 5.117 disc · 312.610 h |
| passos com curso diferente | 88 de 145 | |

O **modelo é idêntico**: o custo de fechar cada um dos 146 cursos bate exatamente
(hora e disciplina). O que diverge é a *ordem* da gulosa: já no passo 1 o
auditor escolhe Música (1.290 h) enquanto o front escolhe SI (1.260 h) — e o
próprio benchmark do auditor diz que SI custa 1.260 h. Diferença de ~0,4% no
total, por escolhas de cota que dependem da ordem.

Outras diferenças conhecidas de definição:

- **`semestres`**: o auditor usa o piso `ceil(CH/carga)`; o front usa o plano
  real (pré-requisitos + teto de CH). O JSON exporta os dois
  (`semestres` e `semestres_plano`).
- O front reenumera os passos depois de tirar o curso-base (o auditor não o
  inclui); antes disso o deslocamento de 1 gerava 120 falsas divergências.

Para o auditor: vale investigar por que `_margem(1250)` no passo 1 é maior que
`score(1250)` (1.260 h) — é o que faz a primeira escolha divergir.


## 10. Artefatos publicados (Fase 6d)

`python -m ufsm_speedrun publicar` gera em `data/public/`:

| arquivo | tamanho | quando o front baixa |
|---|---|---|
| `ufsm-web.db.gz` | 2,1 MB | boot |
| `ementas.db.gz` | 4,1 MB | ao abrir a cadeira (não implementado) |
| `bibliografias.db.gz` | 4,2 MB | ao expandir bibliografia (não implementado) |
| `manifest.json` | — | metadados |

O núcleo tem todas as tabelas do otimizador (`dcg_elegivel`, `eh_terminal`,
`v_equivalencia_efetiva`, `eh_nucleo_comum`) e **não tem texto**: os campos
`programa_texto`/`objetivos_html`/`bibliografia_texto` vêm `NULL`. O front baixa
o `.gz` e descomprime com `DecompressionStream` (sem pako), com fallback para
`./ufsm.db`; drag & drop aceita os dois.

`web/scripts/snapshot-db.py` copia o `.db` e o `.gz` publicados para
`web/public/` (e cai para `data/ufsm.db` se `data/public/` não existir).
