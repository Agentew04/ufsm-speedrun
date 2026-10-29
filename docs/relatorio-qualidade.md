# Relatório de qualidade dos dados

Gerado em 2026-10-29T00:53:15Z por `python -m ufsm_speedrun validar`.

| | verificação | situação |
|---|---|---|
| ✅ | Integridade referencial | 0 violação(ões) de chave estrangeira |
| ✅ | Cursos sem nenhuma versão de currículo | 0 curso(s) |
| ✅ | Cursos sem versão selecionada | 0 curso(s) |
| ✅ | Versões selecionadas sem árvore curricular (Fase 2 falhou?) | 0 versão(ões) |
| ✅ | Ementas (Fase 4) | 11159/11159 baixadas · 10573 com programa · 0 pendentes · 586 sem programa no SIE |
| ⚠️ | Integridade do grafo de pré-requisitos | 3806 arestas · 4 auto-exigência(s) · 0 ciclo(s) real(is) |
| ⚠️ | Coerência de carga horária | 148 versões conferidas · 1 com obrigatórias acima do total |
| ⚠️ | Pré-requisitos e equivalências (Fase 3) | 6031/12313 ofertas com flag · 6031 com relação gravada · 0 pendentes · 4649 arestas de prereq · 5008 itens de equivalência · ❗ 0 prereq e 5 equivalências sem disciplina referenciada |
| ⚠️ | Cotas abertas (sem disciplinas e sem atividades) | 21 cota(s) — precisam de tratamento explícito no otimizador |
| ⚠️ | Adjudicação da banda prioritária (Fase 6b) | 943 pares julgados (equivalente: 478, parcial: 323, nao_equivalente: 142) · 76 fora da banda atual (seguem válidos na view) |
| ✅ | Elegibilidade de DCG | 129 cotas · 15209 pares · 4657 por menu · 1 abertas |

## ✅ Integridade referencial

0 violação(ões) de chave estrangeira

## ✅ Cursos sem nenhuma versão de currículo

0 curso(s)

## ✅ Cursos sem versão selecionada

0 curso(s)

## ✅ Versões selecionadas sem árvore curricular (Fase 2 falhou?)

0 versão(ões)

## ✅ Ementas (Fase 4)

11159/11159 baixadas · 10573 com programa · 0 pendentes · 586 sem programa no SIE

## ⚠️ Integridade do grafo de pré-requisitos

3806 arestas · 4 auto-exigência(s) · 0 ciclo(s) real(is)

- `auto: MSC1272`
- `auto: MSC1259`
- `auto: UFSM00061`
- `auto: UFSM00923`

## ⚠️ Coerência de carga horária

148 versões conferidas · 1 com obrigatórias acima do total

- `Ciências Biológicas - Núcleo Comum (2024): obrigatórias 1110h > total 1080h`

## ⚠️ Pré-requisitos e equivalências (Fase 3)

6031/12313 ofertas com flag · 6031 com relação gravada · 0 pendentes · 4649 arestas de prereq · 5008 itens de equivalência · ❗ 0 prereq e 5 equivalências sem disciplina referenciada

## ⚠️ Cotas abertas (sem disciplinas e sem atividades)

21 cota(s) — precisam de tratamento explícito no otimizador

- `420h · Engenharia de Transportes e Logística (2023) · Extensão`
- `420h · Bacharelado em Sistemas de Informação (2026) · DISCIPLINAS COMPLEMENTARES DE GRADUAÇÃO`
- `180h · Bacharelado em Sistemas de Informação (2026) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO`
- `150h · Arquitetura e Urbanismo (2023) · Núcleo de Planejamento Urbano e Regional`
- `140h · Curso Superior de Tecnologia de Geoprocessamento (2026) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO`
- `135h · Curso de Nutrição/CAMPUS/PM (2023) · 2023`
- `135h · Nutrição (2026) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO`
- `103h · Relações Públicas Bacharelado - CAMPUS UFSM-FW (2027) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO`
- `100h · Ciência de Dados e Inteligência Artificial (2025) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO V`
- `100h · Curso de Ciências Biológicas/CAMPUS/PM (2026) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO`
- `90h · Música e Tecnologia - Bacharelado (2023) · Atividades Complementares de Extensão`
- `90h · Medicina Veterinária (2026) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO`
- `75h · Curso de Segurança Cibernética (2027) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO`
- `75h · Engenharia Ambiental e Sanitária - CAMPUS UFSM-FW (2027) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO`
- `60h · Administração - Noturno (2026) · ATIVIDADES COMPLEMENTARES DE GRADUAÇÃO`

## ⚠️ Adjudicação da banda prioritária (Fase 6b)

943 pares julgados (equivalente: 478, parcial: 323, nao_equivalente: 142) · 76 fora da banda atual (seguem válidos na view)

## ✅ Elegibilidade de DCG

129 cotas · 15209 pares · 4657 por menu · 1 abertas

---

## Contagens

```
curso                        148
versao_curriculo             528
estrutura                   1574
disciplina                 11159
disciplina_curriculo       12313
prereq_item                 6036
equivalencia_item           5008
```
