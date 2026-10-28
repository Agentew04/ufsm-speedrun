# Contrato de dados — para quem está fazendo o frontend

> Documento de coordenação entre duas frentes de trabalho simultâneas:
> **(A) coleta** (pacote `ufsm_speedrun/`) e **(B) frontend** (`web/`).
> Se você é o agente do frontend, leia isto antes de escrever qualquer query.

---

## 1. Regra de ouro

**O frontend é read-only sobre `data/ufsm.db`.** Não escreve, não roda crawl,
não faz request para a UFSM. Se precisar de um dado que não existe, peça — a
coleta é da outra frente.

Não edite nada em `ufsm_speedrun/` (é onde a coleta vive). Seu espaço é `web/`.

## 2. O que existe agora (e o que ainda não)

O banco está **parcialmente preenchido** enquanto a coleta roda:

| fase | estado |
|---|---|
| 0–2 | ✅ completo (148 cursos, 528 versões, 12.313 ofertas, 8.259 disciplinas) |
| 3 | 🚧 em andamento (~30% das ofertas com pré-req/equivalência) |
| 4 | ⏳ não começou (ementas quase todas vazias) |
| 5 | ✅ validação disponível (`validar`) |

**Consequência:** tabelas `prereq_*` e `equivalencia_*` estão incompletas;
`disciplina.programa_texto` está `NULL` para quase tudo. Construa a UI tolerando
isso (estados vazios explícitos, sem quebrar em `NULL`).

Enquanto isso, use `LEFT JOIN` e `COALESCE` em tudo. Nada de `INNER JOIN` em
tabela que pode estar vazia.

## 3. Como conectar

```python
import sqlite3
conn = sqlite3.connect("file:data/ufsm.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA query_only = ON")
```

- `mode=ro` + `query_only`: garante que nenhum bug seu trave a coleta (que
  escreve no mesmo arquivo, em WAL — leitura concorrente é segura).
- **Não** copie o arquivo: WAL tem arquivos `-wal`/`-shm`; copiar só o `.db`
  pode perder os últimos commits.

## 4. Mapa do schema

Esquema completo: `ufsm_speedrun/schema.sql` (14 tabelas + 1 view).
O essencial:

```
disciplina            catálogo GLOBAL (codigo é único: ELC1079)
  └ disciplina_ch     carga horária por tipo de aula (teórica/prática)

curso                 148 cursos; tem campus, campus_slug, modalidade, grau
  └ versao_curriculo  o curso num ano; `selecionada = 1` é a que vale
      └ estrutura     árvore de requisitos ("NÚCLEO BÁSICO", "DCG", ...)
          ├ estrutura_atividade    requisito que não é disciplina
          └ disciplina_curriculo   a OFERTA: disciplina X, neste núcleo, neste papel
                ├ prereq_bloco → prereq_item
                └ equivalencia_bloco → equivalencia_item
```

Atalho pronto, use esta view para quase tudo:

```sql
SELECT * FROM v_disciplina_curriculo;  -- já junta oferta + curso + versão + núcleo + disciplina
-- colunas: oferta_id, versao_id, curso_id, curso, versao_ano, versao_situacao,
--          nucleo, nucleo_ch_minima, disciplina_id, codigo, disciplina, ch,
--          creditos, tipo_item, tipo, periodo_ideal, tem_prereq, tem_equiv
```

### Enums (não invente rótulo novo)

`disciplina_curriculo.tipo_item`:

| item | rótulo | cor sugerida |
|---|---|---|
| 1 | Obrigatória | neutro/branco |
| 2 | Optativa | azul |
| 3 | Eletiva | azul |
| 4 | Atividade Complementar | amarelo |
| 5 | Disciplina Complementar de Graduação (DCG) | verde |
| 6 | Inativa | cinza |
| 7 | DCG de Pós-Graduação | verde-escuro |
| 8 | Atividade Complementar de Pós-Graduação | amarelo-escuro |

`periodo_ideal = 99` significa **"qualquer período"** (típico de DCG) — na UI
mostre "Qualquer", nunca "99".

`prereq_item.tipo_item`: 1 disciplinas · 2 correquisito · 3 CH vencida ·
4 créditos vencidos · 5 período vencido.
Semântica dos blocos: **OR entre blocos, AND dentro do bloco**.

## 5. Queries de referência

**Lista de cursos com contagem**

```sql
SELECT c.id, c.nome, c.campus, c.modalidade, c.grau, v.numero AS versao,
       COUNT(dc.id) AS ofertas
FROM curso c
JOIN versao_curriculo v ON v.curso_id = c.id AND v.selecionada = 1
LEFT JOIN disciplina_curriculo dc ON dc.versao_id = v.id
GROUP BY c.id
ORDER BY c.nome;
```

**Um curso: ofertas por período e papel**

```sql
SELECT periodo_ideal, tipo_item, codigo, disciplina, ch, creditos, tem_prereq, tem_equiv
FROM v_disciplina_curriculo
WHERE curso_id = ? AND versao_situacao IS NOT NULL
ORDER BY CASE WHEN periodo_ideal = 99 THEN 999 ELSE periodo_ideal END, disciplina;
```

**Grafo (nós + arestas) de um curso**

```sql
-- nós
SELECT DISTINCT disciplina_id, codigo, disciplina, ch, tipo_item, periodo_ideal
FROM v_disciplina_curriculo WHERE curso_id = ?;

-- arestas de pré-requisito (podem estar incompletas)
SELECT pi.disciplina_req_id AS origem, dc.disciplina_id AS destino, pb.disciplina_curriculo_id
FROM prereq_item pi
JOIN prereq_bloco pb ON pb.id = pi.bloco_id
JOIN disciplina_curriculo dc ON dc.id = pb.disciplina_curriculo_id
WHERE pi.tipo_item IN (1, 2) AND pi.disciplina_req_id IS NOT NULL;

-- arestas de equivalência
SELECT ei.disciplina_req_id AS origem, dc.disciplina_id AS destino
FROM equivalencia_item ei
JOIN equivalencia_bloco eb ON eb.id = ei.bloco_id
JOIN disciplina_curriculo dc ON dc.id = eb.disciplina_curriculo_id
WHERE ei.disciplina_req_id IS NOT NULL;
```

**KPIs da dashboard**

```sql
SELECT (SELECT COUNT(*) FROM curso)                          AS cursos,
       (SELECT COUNT(*) FROM disciplina)                     AS disciplinas,
       (SELECT COUNT(*) FROM disciplina_curriculo)           AS ofertas,
       (SELECT COUNT(*) FROM versao_curriculo WHERE selecionada = 1) AS versoes,
       (SELECT COUNT(*) FROM disciplina_curriculo WHERE tem_prereq = 1) AS com_prereq,
       (SELECT COUNT(*) FROM disciplina_curriculo WHERE tem_equiv = 1)  AS com_equiv;
```

## 6. Armadilhas que vão te morder na UI

1. **`ch_total` de versão não fecha** com a soma das obrigatórias em pelo menos
   1 curso (Ciências Biológicas – Núcleo Comum/2024). Não exiba "X% concluído"
   calculado assim sem avisar.
2. **21 cotas abertas**: nós com `ch_minima > 0` e zero disciplinas/atividades
   (ex.: DCG de 420 h em Sistemas de Informação/2026). Na UI, mostre como
   "qualquer disciplina — cota aberta", não como lista vazia/quebrada.
3. **Pré-requisito é esparso** (0–20% das disciplinas). Não sugira ao usuário
   que o grafo está completo. Mostre `periodo_ideal` como ordem recomendada.
4. **Uma disciplina aparece em vários cursos** — o nó do grafo deve ser
   `disciplina_id`, não `oferta_id`, senão você duplica tudo entre cursos.
5. **Campi diferentes**: `campus` existe por curso. Disciplinas de campi
   distintos não são intercambiáveis na prática. Ofereça filtro por campus.
6. **Códigos esquisitos** (`042.AGD.MAT.07`): trate como TEXT, nunca parseie.
7. **Ementa vazia ≠ erro**: muitas disciplinas realmente não têm programa no SIE.

## 7. O que vai mudar quando a coleta terminar

- `prereq_item` e `equivalencia_item` cheios (~6 mil ofertas)
- `disciplina.programa_texto` preenchido (a maioria)
- `docs/relatorio-qualidade.md` publicado

Nada de schema muda. Se você já escreveu contra as tabelas acima, continua
funcionando — só vai ter mais dado.

## 8. Estilo visual

Ver `docs/plano.md` §8 (Fase 7): FastAPI + Jinja2, Cytoscape.js para o grafo,
Chart.js para gráficos, **bibliotecas vendorizadas** em `web/static/vendor/`
(nada de CDN — funciona offline), tema escuro por padrão.

> **Atualização (frente B, 2026-10-28):** a dashboard foi feita 100% no cliente
> (`web/`, React + sql.js + Cytoscape), sem FastAPI. Ver `docs/frontend.md`.

---

## 9. Achado da frente B: equivalências gravadas sem a disciplina

`equivalencia_item` está com **4.862 linhas** e **todas** com
`disciplina_req_id = NULL` e `disciplina_req_codigo = NULL`. O payload cru tem o
dado: cada item traz `"disciplina": {"id": ..., "codigo": ...}`. O parser em
`ufsm_speedrun/relacoes.py` (~linha 52) lê `item.get("disciplinaRequisito")`,
que é o campo dos **pré-requisitos**; em equivalências o campo é `disciplina`.

```python
req = item.get("disciplinaRequisito") or item.get("disciplina") or {}
```

Não precisa de novo crawl: `data/raw/curso_equivalenciasAgrupadas/` já tem
4.687 respostas com **5.007 pares** de equivalência. Reprocessar o raw e
reexportar o `.db` basta. Ganho medido (a partir de CC): SI 14/37 obrigatórias
cobertas, Eng. Computação 9, Eng. Produção 6.

O `prereq_*` está correto: 3.071 de 3.101 ofertas com `tem_prereq = 1` já têm
blocos.
