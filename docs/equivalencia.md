# Equivalência entre disciplinas — método e evidências

> Responde à pergunta: *"como comparar a ementa? Levenshtein no nome e depois a LLM julgar?"*
> Resposta curta: **não no nome** — e há dado que mostra por quê.

---

## 1. O experimento

Comparo três sinais contra a única verdade objetiva que temos: as **3.862
equivalências que o próprio SIE declara** (`equivalencia_item`).

- **Positivos**: pares declarados equivalentes.
- **Negativos fáceis**: pares aleatórios.
- **Negativos difíceis**: pares com nome ≥ 0,85 de similaridade que **não** são
  equivalentes — o caso adversário que qualquer regra precisa acertar.

| sinal | positivos (média) | negativos fáceis | negativos difíceis |
|---|---|---|---|
| **Levenshtein no nome** | 0,699 | 0,226 | **0,987** |
| **TF-IDF na ementa** | 0,429 | 0,020 | 0,275 |

A primeira linha é a sentença de morte do Levenshtein-no-nome: os pares com nome
**mais parecido são justamente os que não são equivalentes**. Os campeões:

```
0,971  "TRABALHO DE CONCLUSÃO DE CURSO III"  vs  "... II"
0,971  "SEMINÁRIO VIII - FLAUTA TRANSVERSA"  vs  "SEMINÁRIO III - ..."
0,971  "PROJETO DE INSTALAÇÕES ELÉTRICAS A"  vs  "... B"
0,970  "INSTRUMENTO II - FAGOTE"             vs  "... IV - FAGOTE"
```

Não é coincidência: em disciplina, **o sufixo é o discriminante**. A regra
funciona ao contrário — quanto mais parecido o nome, mais provável que sejam
*sequenciais* e portanto diferentes.

Na prática, um limiar de nome gera **100% de falso positivo** no conjunto difícil,
em qualquer corte de 0,30 a 0,80.

### E a ementa?

Separa de verdade, mas como **ranking**, não como regra binária. Precisão/recall
contra os negativos difíceis:

| limiar de cosseno | recall (oficiais) | falso positivo | precisão aprox. |
|---|---|---|---|
| 0,30 | 62,2% | 27,5% | 69% |
| 0,50 | 37,2% | 14,3% | 72% |
| 0,75 | 16,2% | 9,0% | 64% |

Ou seja: a "regra dos 75% de ementa" que a gente tinha pensado **não existe nos
dados**. Só 16% das equivalências oficiais têm cosseno ≥ 0,75.

## 2. Por que a ementa não fecha 75%

Insight importante: **equivalência no SIE é administrativa, não textual**. Dois
cursos equivalentes costumam ser o mesmo conteúdo *reorganizado* após uma reforma
curricular — nomes de unidades diferentes, bibliografia trocada, ementa reescrita.
O texto muda; o direito acadêmico permanece.

Consequência medida: entre as equivalências oficiais que viraram candidatas
(ementa parecida o bastante para entrar no top-12), recuperamos **41%**. Sobre
todas as 3.862, apenas **8%**.

Isso não invalida o método — reposiciona o objetivo:
> A heurística **não reproduz** a equivalência do SIE. Ela **descobre** pares de
> conteúdo quase idêntico que o SIE **não** declarou (e que, portanto, você pode
> pedir por aproveitamento).

## 3. O funil que faz sentido

```
11.159 disciplinas
   │
   ├─ bloqueio: top-12 vizinhos TF-IDF de cada uma   →  68.607 pares
   │     (nunca 11k² = 62 milhões)
   │
   ├─ filtros duros:
   │     · sufixo sequencial (I≠II, A≠B, 3≠4)         → descarta 29.546
   │     · razão de CH < 0,70                          → descarta 7.656
   │     · ementa curta/genérica (< 20 tokens)
   │     · ementa idêntica + nome diferente (boilerplate)
   │
   └─ score final = 0,62·ementa + 0,14·nome + 0,16·CH + 0,08·departamento
         │
         ├─ ≥ 0,55 e sem impedimento  →  equivalente   (2.325)
         ├─ ≤ 0,22                    →  nao_equivalente (7.863)
         └─ resto                     →  revisar       (58.419)
```

O papel do nome **não é decidir** — é (a) bloquear candidatos e (b) detectar
sequência. É para isso que ele serve bem.

## 4. Onde a LLM entra (e onde não entra)

Não faz sentido pedir opinião sobre 68 mil pares. Mas a banda de revisão se
decompõe assim:

| motivo | pares | avg score | precisa de LLM? |
|---|---|---|---|
| rejeitado por regra (sequência I/II/III) | 29.546 | 0,41 | **não** — a regra resolve |
| ambíguo puro (score médio, sem impedimento) | 20.761 | 0,34 | **não** — sinal fraco demais |
| carga horária incompatível | 7.656 | 0,32 | **não** — a regra de CH resolve |
| ementa curta/genérica | 241 | 0,38 | não |
| **ementa idêntica mas nome diferente** | 215 | **0,89** | **sim** |
| **score ≥ 0,60 sem sequência** | **462** | — | **sim** |

### Como foi feito

Os **462 pares** foram exportados em 10 lotes (`data/exports/lotes/`) e julgados
por 10 subagentes em paralelo, cada um lendo um arquivo e gravando o veredito no
mesmo formato. Nenhum par ficou sem julgamento (47/47 em 9 lotes, 39 no último).

Persistência em tabela **separada** (`equivalencia_julgada`) — o palpite da
heurística nunca é sobrescrito, então dá para comparar os dois e re-julgar.

| veredito | pares | confiança média |
|---|---|---|
| equivalente | **233** | 0,75 |
| parcial | 193 | 0,58 |
| nao_equivalente | 36 | 0,53 |

Dos 233 confirmados, a maioria fora do SIE é **presencial × EaD** da mesma
disciplina — exatamente o tipo de par que o SIE não declara e que rende
aproveitamento:

```
LTC1004 LATIM BÁSICO             ↔ EAD1095 LATIM BÁSICO - EAD
LTV1012 SINTAXE DO PORTUGUÊS     ↔ EAD1081 SINTAXE DO PORTUGUÊS - EAD
EDE1130 LIBRAS: LICENCIATURAS    ↔ EAD2016 LIBRAS: LICENCIATURAS/EAD
ADM2020 CUSTOS                   ↔ CTB1110 FUNDAMENTOS DE CUSTOS
CAD1015 SISTEMAS DE INFORMAÇÃO   ↔ ADM2019 SISTEMAS DE INFORMAÇÕES
```

O CSV completo (`equivalencias-prioritarias.csv`) fica para auditoria.

## 4b. Quanto custou

- 68.607 pares pontuados: ~10 s (CPU, numpy/sklearn)
- 462 pares julgados: 10 subagentes em paralelo, ~2 min
- Cada lote: ~80 KB de JSON, ~20 mil tokens

Ou seja: o funil é o que torna a LLM viável. Sem ele, seriam 68 mil pares.

## 5. A regra de negócio, corrigida

O que a gente tinha:

> CH do candidato ≥ CH do alvo **e** ementa ≥ 75% igual

O que os dados pedem:

1. **CH**: manter, mas como *razão* (min/max ≥ 0,70), não como igualdade.
   Uma disciplina de 45 h pode cobrir 30 h; o contrário não.
2. **Ementa**: usar como score contínuo, com limiar calibrado (0,55 no composto,
   não 0,75), nunca como regra binária.
3. **Sequência**: filtro rígido. É o que mais reduz falso positivo.
4. **LLM**: só na faixa 0,60–0,90 e sem conflito de sequência.

## 6. Resultado atual

```
pares candidatos ........... 68.607
equivalência automática .... 2.325
banda de revisão ........... 58.419   (462 prioritários)
descartados ................ 7.863
recall sobre as oficiais ... 8,0%  (41% entre as que viraram candidatas)
tempo ...................... ~10 s
```

Exemplos de descoberta (mesmo nome, mesma CH, ementa idêntica, código diferente):

```
DAC1112 DIREÇÃO TEATRAL II      ↔ DAC1159 DIREÇÃO TEATRAL II
CSEE4024 ORGANIZAÇÃO E ADM...   ↔ CSEM4029 ORGANIZAÇÃO E ADM...
EDE1045 LIBRAS                  ↔ EDE1090 LIBRAS
DCOM1003 REDES DE COMPUTADORES  ↔ UFSM01304 REDES DE COMPUTADORES
```

Esses são o produto: pares que o SIE **não** declarou equivalentes e que podem
virar pedido de aproveitamento.

## 7. Limitações declaradas

- **Ementa ausente**: 427 disciplinas sem programa no SIE e ~3 mil que só aparecem
  como referência de equivalência (não estão em currículo nenhum). Elas entram no
  grafo pelo código, mas não pelo texto.
- **Boilerplate**: disciplinas de música/artes compartilham ementa genérica; daí a
  regra "ementa idêntica + nome diferente → revisar".
- **Recall baixo contra o oficial** é esperado e não é falha: são conceitos
  diferentes de equivalência (§2).
- Os pesos do score são heurísticos, calibrados à mão sobre a distribuição dos
  pares oficiais. Ajustáveis em `equivalencia.Config`.

## 8. Como rodar

```powershell
.\.venv\Scripts\python.exe -m ufsm_speedrun equivalencia
.\.venv\Scripts\python.exe -m ufsm_speedrun equivalencia --limiar 0.60 --top-k 20
```

Saídas: tabela `similaridade_ementa` e os dois CSVs em `data/exports/`.
