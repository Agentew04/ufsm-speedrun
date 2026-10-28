# API do SIE/UFSM — documentação de engenharia reversa

> **Status:** levantado em 2026-10-28, por inspeção do JavaScript do próprio portal.
> **Fonte da verdade:** este documento. Se algo divergir do site, o site mudou — atualize aqui.

---

## 1. Visão geral

O site `ufsm.br` é WordPress. As páginas de curso **não** contêm os dados curriculares no HTML:
elas entregam um "esqueleto" com `div`s vazias e um JS que busca tudo em um webservice JSON
chamado **SIE** (Sistema de Informações para o Ensino), hospedado em outro host.

```
site (www.ufsm.br)                        webservice (portal.ufsm.br)
─────────────────────────────────────     ─────────────────────────────────────────
/graduacao                          ──►   (HTML server-side: lista dos 110 cursos)
/cursos/graduacao/<campus>/<slug>/        (HTML: só IDs de curso + versões)
  informacoes-do-curriculo          ──►   /webservice/ws/site/curso/estrutura.json
                                          /webservice/ws/site/curso/disciplinasPeriodo.json
                                          /webservice/ws/site/curso/preRequisitosAgrupados.json
                                          /webservice/ws/site/curso/equivalenciasAgrupadas.json
/ementario/disciplinas/<CODIGO>     ──►   /webservice/ws/site/disciplina/disciplina.json
/ementario/disciplinas              ──►   /webservice/ws/site/disciplina/busca.json
                                          /webservice/ws/site/disciplina/curriculos.json
```

**Conclusão prática:** não é preciso `selenium`/`playwright` nem fazer scraping de HTML
para os dados curriculares. As únicas páginas HTML necessárias são a lista de cursos e a
página de currículo de cada curso (para descobrir IDs).

### Host e autenticação

```
BASE = https://portal.ufsm.br/webservice/ws/site
```

Todas as chamadas são `POST` e exigem **um único header**:

```
X-UFSM-Application-ID: SiteWS
```

Sem ele a resposta é HTTP 200 com corpo de erro (não é 401!):

```json
{"error": true, "className": "JsonError", "codigo": 500, "mensagem": "Acesso não autorizado"}
```

`Accept: application/json` é opcional. Encoding das respostas: **UTF-8**.
Não há token, cookie, CSRF nem API key. Não há rate limit documentado nem headers
`X-RateLimit-*` / `Retry-After`.

### Formato de erro

Todo objeto pode vir com envelope de erro:

```json
{"error": true, "className": "JsonError", "codigo": 500, "mensagem": "..."}
```

Regra: **sempre checar `error == true`** antes de consumir, mesmo com HTTP 200.

---

## 2. Endpoint: estrutura curricular (o principal)

```
POST /curso/estrutura.json
Content-Type: application/x-www-form-urlencoded
X-UFSM-Application-ID: SiteWS

versao=<id_versao>&disciplinas=true
```

| Param | Tipo | Obrigatório | Nota |
|---|---|---|---|
| `versao` | int | sim | ID de **versão de currículo** (não é o ID do curso) |
| `disciplinas` | bool | não | `false`/omitido → árvore de núcleos **vazia** (sem disciplinas). Use `true`. |

### Resposta

```
JsonCollection
└── itens: EstruturaCurricular[]      ← normalmente 2 raízes
    ├── id
    ├── descricao                      "DISCIPLINAS DO CURRÍCULO FIXO"
    ├── cargaHorariaMinima / Maxima    cota de horas do núcleo (nullable)
    ├── minimoCreditos / maximoCreditos
    ├── atividades: [{id, descricao}]  requisitos que NÃO são disciplina
    ├── disciplinas: DisciplinaCurriculo[]
    └── filhas: EstruturaCurricular[]
```

Exemplo real (Ciência da Computação, versão 2024 = `104760`):

```
[DISCIPLINAS DO CURRÍCULO FIXO]
  ├── NÚCLEO DE FORMAÇÃO BÁSICA                     chMin=1200   19 disciplinas
  ├── NÚCLEO DE FORMAÇÃO COMPLEMENTAR E HUMANÍSTICA  chMin=240     4 disciplinas
  └── NÚCLEO DE FORMAÇÃO TECNOLÓGICA                chMin=900    14 disciplinas
[DISCIPLINAS DO CURRÍCULO FLEXÍVEL]
  ├── ATIVIDADES COMPLEMENTARES DE EXTENSÃO         chMin=0       7 atividades
  ├── ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO        chMin=150
  │     └── ... Versão 2024                         chMin=150     8 atividades
  └── DISCIPLINAS COMPLEMENTARES DE GRADUAÇÃO       chMin=480    57 disciplinas
```

**Isso é uma árvore de requisitos, não uma lista de cadeiras.** Cada nó é um "cumpra
`chMinima` horas escolhendo entre estas disciplinas" — ou seja, um problema de mochila.

⚠️ **Ordenação:** o wesbservice devolve as `filhas` ordenadas alfabeticamente, mas o SIE
ordena por `id`. O JS do site reordena por `id` para exibir na ordem original. Se a ordem
importar (ex.: ordem dos núcleos), reordene `filhas` por `id` crescente.

### `DisciplinaCurriculo` (a oferta de uma disciplina numa versão)

```jsonc
{
  "id": 148601,                         // ← PK da oferta; use ESTE id para prereq/equivalência
  "estrutura": { "id": 37356, ... },    // núcleo onde ela mora
  "disciplina": { /* ver §3 */ },
  "tipo": { "item": 1, "descricao": "Obrigatória" },
  "periodoIdeal": 3,                    // 99 = "qualquer período" (típico de DCG)
  "cargaHorariaEad": null,
  "notaMinima": 5.0,
  "notaMaxima": 10,
  "temPreRequisitos": false,
  "temEquivalencias": false
}
```

### Enum `tipo.item` de `DisciplinaCurriculo`

| item | Papel no currículo | Cor no site |
|---|---|---|
| 1 | Obrigatória | branco |
| 2 | Optativa | azul |
| 3 | Eletiva | azul |
| 4 | Atividade Complementar | amarelo |
| 5 | Disciplina Complementar de Graduação (DCG) | verde |
| 6 | Inativa | cinza |
| 7 | DCG de Pós-Graduação | verde |
| 8 | Atividade Complementar de Pós-Graduação | amarelo |

> `descricao` vem preenchida nos endpoints de curso, mas na prática o texto exato é
> `"Disciplina Complementar de Graduação"` para DCG. **Sempre usar `tipo.item`** como chave,
> `descricao` só como rótulo.

---

## 3. Endpoint: detalhe global da disciplina (ementa)

```
POST /disciplina/disciplina.json
X-UFSM-Application-ID: SiteWS
Content-Type: application/x-www-form-urlencoded

codigo=<codigo_da_disciplina>          // ex.: ELC1079
```

Resposta: objeto `Disciplina` (não vem embrulhado em coleção).

```jsonc
{
  "id": 81751,
  "codigo": "ELC1079",
  "descricao": "ARQUITETURAS DE COMPUTADORES \"A\"",
  "nomeIngles": "COMPUTER ARCHITECTURE \"A\"",
  "departamento": { "id": 619, "descricao": "...", "codigo": "..." },
  "situacao": { "codigo": "A", "descricao": "Ativa" },
  "creditos": 4,
  "cargaHoraria": 60,
  "encargoDidatico": 60,
  "cargaHorariaExtensao": null,
  "cargasHorarias": [ { "tipoAula": {"item":2,"descricao":"Teórica"}, "horasAula": 60 } ],
  "objetivos": "<p>Conhecer os conceitos...</p>",
  "ementa": null,                        // ⚠️ SEMPRE null no SIE
  "documentoPrograma": 8790024,          // id do PDF no portal de documentos (nullable)
  "programaDisciplina": [ /* ver abaixo */ ]
}
```

### 🔑 Onde está a ementa

O campo `ementa` é **sempre `null`**. O conteúdo programático real está em
`programaDisciplina`, uma lista de `ProgramaDisciplina`:

```jsonc
{
  "id": 76312,
  "descricao": "UNIDADE 1 - INTRODUÇÃO",
  "texto": "<p><span style=\"font-size:10pt;\">1.1 - Modos de endereçamento.</span></p>...",
  "tipoConteudo": { "item": 2, "descricao": "Programa da Disciplina" },
  "filhos": null                          // pode ter subitens (recursivo)
}
```

| `tipoConteudo.item` | Significado |
|---|---|
| 1 | Bibliografia |
| 2 | Programa da Disciplina (é a "ementa" de fato) |

Para o cálculo de similaridade de ementas (regra dos 75%), use:
`objetivos` + todos os `texto` de `tipoConteudo 2` (recursivo em `filhos`), normalizados.
Bibliografia (tipo 1) é ruído para esse fim — guarde separado.

### PDF "Programa Autenticado"

`documentoPrograma` é um ID de documento: `https://portal.ufsm.br/documentos/publico/documento.html?id=<id>`.
Útil como fonte alternativa/auditável. **Não** é necessário para a Fase 1–4.

---

## 4. Endpoint: disciplinas por período ideal

```
POST /curso/disciplinasPeriodo.json
versao=<id_versao>
```

Resposta: `DisciplinaCurriculo[][]` — na prática, `[{periodo: int, disciplinas: [...]}, ...]`
agrupado por `periodoIdeal`. O site usa isso só para renderizar as abas por semestre.

**É redundante com `estrutura.json?disciplinas=true`** (mesmos `DisciplinaCurriculo.id`),
mas é mais leve e é a forma mais simples de saber "quais disciplinas e em que semestre".
Use como alternativa ou como verificação cruzada.

Retorno observado (CC 2024):
`[(1,5), (2,6), (3,6), (4,5), (5,6), (6,4), (7,4), (8,1), (99,57)]`  ← 99 = DCGs

---

## 5. Endpoint: pré-requisitos

```
POST /curso/preRequisitosAgrupados.json
disciplina=<DisciplinaCurriculo.id>     // ⚠️ é o id da OFERTA, não o id da disciplina
```

Resposta: `Bloco[]`. Semântica: **OR entre blocos, AND dentro do bloco**.

```
[
  {
    "bloco": { "item": 5, "descricao": "BLOCO 20" },
    "tipos": [
      {
        "tipo": { "item": 1, "descricao": "Disciplina" },
        "itens": [ /* PreRequisito */ ]
      }
    ]
  }
]
```

Retorna `[]` quando não há pré-requisito.

### Enum `tipo.item` de pré-requisito

| item | Significado | Campos usados |
|---|---|---|
| 1 | Disciplinas vencidas | `disciplinaRequisito.{id,codigo,descricao}` |
| 2 | Correquisito (vencida **ou** matriculada) | igual ao 1 |
| 3 | Carga horária mínima em estrutura curricular | `estruturaCurricular.descricao`, `numeroReferencia` (horas) |
| 4 | Créditos vencidos | `numeroReferencia` (créditos) |
| 5 | Período vencido | `numeroReferencia` (nº do período) |

Item de exemplo (`tipo` 1):

```jsonc
{
  "disciplinaRequisito": { "id": 82210, "codigo": "ELC1086",
                           "descricao": "METODOLOGIA DE PESQUISA EM INFORMÁTICA",
                           "creditos": 2, "cargaHoraria": 60 },
  "disciplinaCurriculoRequisito": { "id": 148621, "periodoIdeal": 99 },
  "tipo": { "item": 1, "descricao": "Disciplina Vencida" }
}
```

> ⚠️ **Qualidade dos dados:** o grafo oficial é **esparso e inconsistente**.
> Medições: CC/2024 → 2 de 94 disciplinas com prereq (2%); CC/2010 → 0 de 101;
> Eng. Computação/2023 → 17 de 124 (14%); Letras/2025 → 12 de 61 (20%).
> Ex.: "Estruturas de Dados" não tem prereq em CC/2024. Não confie nisso como grafo
> completo — use `periodoIdeal` como sinal de sequenciamento.

---

## 6. Endpoint: equivalências

```
POST /curso/equivalenciasAgrupadas.json
disciplina=<DisciplinaCurriculo.id>
```

Mesma estrutura de blocos dos pré-requisitos. Semântica:
**para obter equivalência é preciso ter sido aprovado em TODAS as disciplinas de UM bloco.**

```jsonc
[
  {
    "bloco": { "item": 1, "descricao": "BLOCO 1" },
    "tipos": [
      { "tipo": { "item": 1, "descricao": "Disciplina Vencida" },
        "itens": [
          { "disciplina": { "id": 30858, "codigo": "STC303",
                            "descricao": "ESTATÍSTICA", "creditos": 4, "cargaHoraria": 60 },
            "disciplinaCurriculoRef": null,
            "tipo": { "item": 1, "descricao": "Disciplina Vencida" } }
        ]
      }
    ]
  }
]
```

`disciplinaCurriculoRef`, quando não-nulo, aponta para a oferta específica (curso+versão)
da disciplina equivalente. `tipo.item == 1` = "Disciplina Vencida" (o caso normal).

**Densidade é boa:** CC/2024 9/94 (10%), CC/2010 13/101 (13%), Eng. Comp. 59/124 (48%),
Letras 38/61 (62%). É a fonte mais rica para o "aproveitamento entre cursos".

---

## 7. Endpoint: busca no catálogo (paginado)

```
POST /disciplina/busca.json
Content-Type: application/json
X-UFSM-Application-ID: SiteWS

{
  "targetPage": 0,                       // 0-based
  "maxResults": 200,                     // testado até 200 OK (2000 → erro/0)
  "params": { "keyword": "CIC" },        // ⚠️ mínimo 3 caracteres
  "orderBy": ["nome", "codigo desc"]
}
```

Resposta:

```jsonc
{
  "error": false,
  "className": "JsonPagedListResponse",
  "validate": { "keyword": "Informe no mínimo 3 caracteres" },  // se inválido
  "count": 178,                            // TOTAL de resultados
  "search": [ Disciplina, ... ]            // página atual
}
```

Observações:
- `keyword` vazio ou < 3 chars → `count: 0` e mensagem em `validate`. **Não dá para listar
  "tudo" com string vazia.**
- A busca é por **substring** em nome **ou** código (`"CIC"` trouxe 178 resultados,
  incluindo `NUT1046 ANTROPOMETRIA NOS CICLOS DE VIDA`). Não é prefixo de código.
- `count` é o total → pagine com `targetPage` e `maxResults` até cobrir.
- `/disciplina/busca.json` é rápido (~0,1–0,7 s).
- Estratégia para enumerar o catálogo inteiro: varrer tokens de 3 letras (A-Z, 0-9) e
  deduplicar por `id`. Não é necessário para a Fase 1–4 (o catálogo real vem dos currículos).

---

## 8. Endpoint: índice reverso (em quais cursos está)

```
POST /disciplina/curriculos.json
disciplina=<Disciplina.id>              // ⚠️ agora é o id GLOBAL da disciplina
```

Resposta: `JsonCollection` com `itens: DisciplinaCurriculo[]`, cada um com
`estrutura → versaoCurso → curso` preenchidos.

⚠️ Atenção à pegadinha: `preRequisitosAgrupados` / `equivalenciasAgrupadas` usam
`DisciplinaCurriculo.id`; `curriculos.json` usa `Disciplina.id`. São IDs diferentes.

---

## 9. Descoberta de cursos e versões (a única parte que é HTML)

### Lista de cursos

`GET https://www.ufsm.br/graduacao`

Está server-side em `#lista_cursos`. Os `<a>` usam **href sem aspas** (detalhe que quebra
regex ingênua):

```html
<li class="col-lg-6 area_400">
  <a class='d-block text-wrap' href=/cursos/graduacao/santa-maria/artes-cenicas/ title='ABI - Artes Cênicas'>ABI - Artes Cênicas</a>
</li>
```

Regex que funciona:
`<a class='d-block text-wrap' href=(/cursos/graduacao/[^ >]+) title='([^']*)'`

Resultado medido: **110 cursos**, **103 slugs únicos** (um slug pode ter vários cursos).
Distribuição: santa-maria 80, educacao-a-distancia 11, frederico-westphalen 7,
cachoeira-do-sul 6, palmeira-das-missoes 6.

### Versões de currículo

`GET .../cursos/graduacao/<campus>/<slug>/informacoes-do-curriculo`

Duas informações no HTML:

1. IDs de curso: `data-ufsm-curso-id="(\d+)"` (pode haver mais de um no mesmo slug)
2. Versões, cada uma com o JSON completo de metadados no atributo (HTML-escapado):

```html
<select id="select-versao-curriculo-701" data-ufsm-curso-id="701" data-ufsm-curso-nivel="3">
  <option value="104760" selected data-versao='{"error":false,"className":"VersaoCurso", ...}'>2024 – Ano: 2024 (Corrente)</option>
  <option value="102214"          data-versao='{...}'>2010 – Ano: 2010 (Ativa)</option>
  ...
</select>
```

Regex: `<option\s+value="(\d+)"[^>]*data-versao='([^']+)'` + `html.unescape` + `json.loads`.

O JSON da versão (`VersaoCurso`) já traz tudo que você precisa:

```jsonc
{
  "id": 104760,
  "curso": { "id": 701, "codigo": "307", "descricao": "Ciência da Computação - Bacharelado",
             "grau": "BACHAREL EM CIÊNCIA DA COMPUTAÇÃO", "codigoEmec": "13881",
             "modalidade": {"descricao":"Bacharelado"}, "turno": {"descricao":"Diurno"},
             "classificacao": {"descricao":"Presencial"}, "nivel": {"item":3},
             "areaConhecimento": {"codigo":"1.00.00.00"},
             "unidade": {"sigla":"..."}, "url": "http://www.inf.ufsm.br/" },
  "numero": "2024", "descricao": "2024",
  "situacao": { "codigo": "C", "descricao": "Corrente" },
  "cargaHorariaTotal": 3300, "cargaHorariaExtensao": 330,
  "cargaHorariaMinima": 275, "cargaHorariaMaxima": 540,
  "periodoIdeal": 8, "periodoMinimo": 6, "periodoMaximo": 12,
  "trancamentosTotais": 4, "trancamentosParciais": 9,
  "tipoPeriodo": { "item": 200, "descricao": "Semestral." }
}
```

`situacao.codigo`: `C` = Corrente, `A` = Ativa (legado ainda vigente p/ quem entrou antes),
`I` = Inativa.

`nivel.item`: `3` = Graduação, `6`/`10`/`16` = Pós-graduação.
`tipoPeriodo.item`: `100`=Ano, `200`=Semestre, `300`=Trimestre, `400`=Etapa.

---

## 10. Armadilhas catalogadas

| # | Armadilha | Impacto | Mitigação |
|---|---|---|---|
| 1 | Header `X-UFSM-Application-ID` obrigatório, erro vem como HTTP 200 | falha silenciosa | checar `error` sempre |
| 2 | `ementa` é sempre `null` | sem ementa | usar `programaDisciplina` (tipo 2) + `objetivos` |
| 3 | `estrutura.json` sem `disciplinas=true` volta sem disciplinas | árvore vazia | sempre passar `true` |
| 4 | DCG pode vir **sem nenhuma disciplina** (só cota de horas) | ex.: SI/2026: DCG `chMin=420`, 0 disciplinas | modelar "bucket aberto" |
| 5 | Pré-requisitos esparsos (0–20%) | grafo pobre | usar `periodoIdeal` como sinal + opcionalmente PPC em PDF |
| 6 | IDs: `DisciplinaCurriculo.id` vs `Disciplina.id` | endpoint errado | ver §5/§6 vs §8 |
| 7 | `filhas` ordenadas alfabeticamente pela WS, não por `id` | ordem dos núcleos errada | reordenar por `id` |
| 8 | `busca.json` exige keyword ≥ 3 chars | não lista tudo | varrer tokens ou ignorar |
| 9 | Um slug pode ter vários cursos (`letras` = 4) | perda de curso | coletar todos os `data-ufsm-curso-id` |
| 10 | Links de curso em `/graduacao` têm `href` sem aspas | regex falha | usar regex tolerante |
| 11 | Latência alta em `estrutura.json` (~3 s, ~280 KB) | crawl lento | cache em disco + pacing |
| 12 | Códigos heterogêneos (`042.AGD.MAT.07`) | parsing ingênuo quebra | `codigo` é TEXT, nunca parsear |
| 13 | Disciplinas inativas ainda aparecem em versões antigas | poluição | filtrar por `situacao` e `versao.situacao` |
| 14 | Duas chamadas ao mesmo endpoint com params diferentes têm `id` de oferta diferente | dedupe errado | chave = `(versao, estrutura, disciplina)` |

---

## 11. Rastreabilidade (de onde veio isto)

Arquivos JS/Documentos inspecionados (URLs estáveis, versão na query string):

| Arquivo | Papel |
|---|---|
| `https://www.ufsm.br/app/themes/ufsm/js/ufsm.js?ver=1.5` | define `ufsm.webservice.host = https://portal.ufsm.br` |
| `https://www.ufsm.br/app/mu-plugins/ufsm-sie/utils/modules/http/http.js?ver=1.4.4` | define o header `X-UFSM-Application-ID: SiteWS` |
| `https://www.ufsm.br/app/mu-plugins/ufsm-sie/apps/cursos/assets/curso-estrutura.js?ver=2.4.0` | endpoints de curso, enums `TR_DISCIPLINA_CLASSE`, semântica de blocos |
| `https://www.ufsm.br/app/mu-plugins/ufsm-sie/apps/ementario/assets/disciplina.js?ver=1.4.0` | endpoint `disciplina.json`, `tipoConteudo` |
| `https://www.ufsm.br/app/mu-plugins/ufsm-sie/apps/ementario/assets/busca-disciplinas.js?ver=1.1.1` | endpoint `busca.json`, paginação |

Cópias locais desses arquivos ficaram em `_probe/` (descartáveis).

---

## 12. Política de uso (importante)

Não há rate limit exposto, mas o serviço é público e lento. Regras adotadas no projeto:

- **1 request por vez**, intervalo mínimo **1,75 s** (± jitter), sem paralelismo.
- `User-Agent` identificável: `ufsm-speedrun/0.1 (projeto acadêmico UFSM)`.
- Backoff exponencial em 429/5xx/timeout (1, 2, 4, 8 s), máx. 4 tentativas.
- `robots.txt` do site: libera `/cursos/**` e `/ementario/**`; disallows só
  `/wp-admin/`, `/wp-includes/`, `/wp-content/`, `/wp-json*` — respeitados.
- **Toda resposta é gravada em disco.** Um crawl completo é feito **uma vez**;
  reprocessamentos leem o cache local.
- Rodar fora de horário comercial (a UFSM usa isso para processos acadêmicos).
