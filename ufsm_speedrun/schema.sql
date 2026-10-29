-- =============================================================================
-- ufsm-speedrun :: esquema do banco
-- =============================================================================
-- Modelo em 3 níveis:
--   disciplina        -> catálogo GLOBAL (chave = código, ex. ELC1079)
--   curso             -> o curso, independente de versão
--   versao_curriculo  -> o curso num ano (o que realmente tem currículo)
--
-- E a árvore de requisitos:
--   versao_curriculo 1--N estrutura (nós: "NÚCLEO BÁSICO", "DCG", ...)
--   estrutura        1--N disciplina_curriculo  (a oferta: disciplina X, neste
--                                                 núcleo, neste papel)
--
-- Por que separar disciplina de disciplina_curriculo:
--   a mesma disciplina aparece em vários cursos com papel/período diferentes.
--   Só com essa separação dá para responder "já cumpri isso em outro curso?".
-- =============================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- -----------------------------------------------------------------------------
-- Controle de ingestão (rastreabilidade do crawl)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingest_run (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fase        TEXT NOT NULL,             -- discover | curriculos | prereqs | ementas
    iniciado_em TEXT NOT NULL,
    finalizado_em TEXT,
    raw_dir     TEXT,
    observacoes TEXT
);

-- -----------------------------------------------------------------------------
-- Catálogo global de disciplinas
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disciplina (
    id                INTEGER PRIMARY KEY,   -- Disciplina.id (SIE)
    codigo            TEXT NOT NULL UNIQUE,  -- ELC1079, 042.AGD.MAT.07, ...
    nome              TEXT NOT NULL,
    nome_ingles       TEXT,
    creditos          INTEGER,
    ch_total          INTEGER,               -- cargaHoraria
    ch_extensao       INTEGER,
    ch_encargo        INTEGER,               -- encargoDidatico
    departamento_id   INTEGER,
    departamento_nome TEXT,
    situacao_codigo   TEXT,                  -- A / I
    situacao          TEXT,                  -- Ativa / Inativa
    tipo              TEXT,                  -- "Disciplina", ...
    tipo_disciplina   TEXT,                  -- Regular / ...
    -- Ementa: o campo `ementa` do SIE é sempre null. O conteúdo real vem de
    -- programaDisciplina (tipoConteudo 2) + objetivos. Guardamos já normalizado.
    objetivos_html    TEXT,
    programa_texto    TEXT,                  -- texto corrido, normalizado
    bibliografia_texto TEXT,                 -- tipoConteudo 1 (separado de propósito)
    documento_programa INTEGER,              -- id do PDF no portal de documentos
    -- Disciplina "terminal": TCC/TCG/TG, estágio, monografia. Não é transferível
    -- entre cursos, então nunca entra em cota de DCG.
    eh_terminal       INTEGER NOT NULL DEFAULT 0,
    terminal_categoria TEXT,                 -- tcc | estagio | monografia
    terminal_motivo   TEXT,
    raw_file          TEXT,                  -- caminho do bruto que originou a linha
    atualizado_em     TEXT
);

CREATE INDEX IF NOT EXISTS idx_disciplina_codigo ON disciplina(codigo);
CREATE INDEX IF NOT EXISTS idx_disciplina_nome   ON disciplina(nome);

-- Quebra de carga horária por tipo de aula (Teórica / Prática / ...)
CREATE TABLE IF NOT EXISTS disciplina_ch (
    disciplina_id INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
    tipo_aula     TEXT NOT NULL,
    horas         INTEGER NOT NULL,
    PRIMARY KEY (disciplina_id, tipo_aula)
);

-- -----------------------------------------------------------------------------
-- Cursos e versões
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS curso (
    id               INTEGER PRIMARY KEY,   -- Curso.id (SIE)
    codigo           TEXT,                  -- 307
    nome             TEXT NOT NULL,         -- nome oficial do SIE
    nome_lista       TEXT,                  -- nome exibido em /graduacao ("ABI - X")
    nome_unificado   TEXT,
    grau             TEXT,
    modalidade       TEXT,                  -- Bacharelado / Licenciatura / ...
    turno            TEXT,
    nivel_item       INTEGER,               -- 3 = graduação
    classificacao    TEXT,                  -- Presencial / EaD
    area_conhecimento TEXT,
    unidade_sigla    TEXT,
    codigo_emec      TEXT,
    url              TEXT,
    campus           TEXT,                  -- rótulo: "Santa Maria", "EaD", ...
    campus_slug      TEXT,                  -- segmento da URL: santa-maria, ...
    slug             TEXT,                  -- slug do curso na URL
    -- ABI / núcleo comum: NÃO é curso completo, é a porta de entrada para uma
    -- habilitação. Calculado no ETL (ver classificacao.py), não na UI.
    eh_nucleo_comum  INTEGER NOT NULL DEFAULT 0,
    nucleo_comum_motivo TEXT
);

CREATE INDEX IF NOT EXISTS idx_curso_campus ON curso(campus_slug);
CREATE INDEX IF NOT EXISTS idx_curso_nucleo ON curso(eh_nucleo_comum);

CREATE TABLE IF NOT EXISTS versao_curriculo (
    id                  INTEGER PRIMARY KEY, -- VersaoCurso.id
    curso_id            INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
    numero              TEXT,                -- "2024", "92"
    ano                 INTEGER,
    situacao_codigo     TEXT,                -- C / A / I
    situacao            TEXT,                -- Corrente / Ativa / Inativa
    ch_total            INTEGER,
    ch_extensao         INTEGER,
    ch_min_periodo      INTEGER,
    ch_max_periodo      INTEGER,
    periodo_ideal       INTEGER,
    periodo_minimo      INTEGER,
    periodo_maximo      INTEGER,
    tipo_periodo_item   INTEGER,             -- 100 Ano / 200 Semestre / ...
    tipo_periodo        TEXT,
    trancamentos_totais INTEGER,
    trancamentos_parciais INTEGER,
    -- 1 = versão escolhida para análise ("Corrente" por padrão)
    selecionada         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (curso_id, numero)
);

CREATE INDEX IF NOT EXISTS idx_versao_curso ON versao_curriculo(curso_id);

-- -----------------------------------------------------------------------------
-- Árvore de requisitos
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS estrutura (
    id          INTEGER PRIMARY KEY,         -- EstruturaCurricular.id
    versao_id   INTEGER NOT NULL REFERENCES versao_curriculo(id) ON DELETE CASCADE,
    pai_id      INTEGER REFERENCES estrutura(id) ON DELETE CASCADE,
    descricao   TEXT NOT NULL,
    ch_minima   INTEGER,
    ch_maxima   INTEGER,
    min_creditos INTEGER,
    max_creditos INTEGER,
    ordem       INTEGER                      -- posição entre irmãos (ordenado por id)
);

CREATE INDEX IF NOT EXISTS idx_estrutura_versao ON estrutura(versao_id);
CREATE INDEX IF NOT EXISTS idx_estrutura_pai    ON estrutura(pai_id);

-- Requisitos que NÃO são disciplinas (ex.: "Participação em evento", horas de
-- extensão). Não entram no grafo, mas contam para fechar o curso.
CREATE TABLE IF NOT EXISTS estrutura_atividade (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    estrutura_id INTEGER NOT NULL REFERENCES estrutura(id) ON DELETE CASCADE,
    sie_id       INTEGER,
    descricao    TEXT
);

-- -----------------------------------------------------------------------------
-- A oferta: disciplina dentro de uma versão/núcleo (com papel e período)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disciplina_curriculo (
    id             INTEGER PRIMARY KEY,      -- DisciplinaCurriculo.id
    versao_id      INTEGER NOT NULL REFERENCES versao_curriculo(id) ON DELETE CASCADE,
    estrutura_id   INTEGER NOT NULL REFERENCES estrutura(id) ON DELETE CASCADE,
    disciplina_id  INTEGER NOT NULL REFERENCES disciplina(id),
    tipo_item      INTEGER NOT NULL,         -- 1 Obrig | 2 Optativa | 3 Eletiva
                                             -- 4 Ativ.Comp | 5 DCG | 6 Inativa | 7/8 pós
    tipo           TEXT,
    periodo_ideal  INTEGER,                  -- 99 = "qualquer" (típico de DCG)
    ch_ead         INTEGER,
    nota_minima    REAL,
    nota_maxima    REAL,
    tem_prereq     INTEGER NOT NULL DEFAULT 0,
    tem_equiv      INTEGER NOT NULL DEFAULT 0,
    -- "Período vencido" (tipo 5): precisa ter vencido este período, logo pode
    -- cursar a partir de periodo_minimo + 1. Requisitos de CH por estrutura
    -- ficam na tabela requisito_ch (podem ser vários por oferta).
    periodo_minimo INTEGER,
    UNIQUE (versao_id, estrutura_id, disciplina_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_periodo ON disciplina_curriculo(periodo_minimo);

-- "Carga horária vencida numa estrutura" (tipo 3). Uma linha por estrutura
-- exigida; `estrutura_id` NULL significa "GERAL" (total do curso).
CREATE TABLE IF NOT EXISTS requisito_ch (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    disciplina_curriculo_id INTEGER NOT NULL
                            REFERENCES disciplina_curriculo(id) ON DELETE CASCADE,
    estrutura_id           INTEGER REFERENCES estrutura(id),
    estrutura_texto        TEXT,
    horas                  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reqch_dc ON requisito_ch(disciplina_curriculo_id);

CREATE INDEX IF NOT EXISTS idx_dc_versao    ON disciplina_curriculo(versao_id);
CREATE INDEX IF NOT EXISTS idx_dc_estrutura ON disciplina_curriculo(estrutura_id);
CREATE INDEX IF NOT EXISTS idx_dc_disc      ON disciplina_curriculo(disciplina_id);
CREATE INDEX IF NOT EXISTS idx_dc_tipo      ON disciplina_curriculo(tipo_item);

-- -----------------------------------------------------------------------------
-- Pré-requisitos: OR entre blocos, AND dentro do bloco
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prereq_bloco (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    disciplina_curriculo_id INTEGER NOT NULL
                            REFERENCES disciplina_curriculo(id) ON DELETE CASCADE,
    sie_item               INTEGER,          -- "BLOCO 20"
    sie_descricao          TEXT
);

CREATE INDEX IF NOT EXISTS idx_pb_dc ON prereq_bloco(disciplina_curriculo_id);

CREATE TABLE IF NOT EXISTS prereq_item (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    bloco_id              INTEGER NOT NULL REFERENCES prereq_bloco(id) ON DELETE CASCADE,
    tipo_item             INTEGER NOT NULL,  -- 1 disciplinas | 2 correquisito
                                             -- 3 CH vencida | 4 créditos | 5 período
    tipo                  TEXT,
    disciplina_req_id     INTEGER REFERENCES disciplina(id),
    disciplina_req_codigo TEXT,
    numero_referencia     INTEGER,           -- horas, créditos ou nº do período
    estrutura_ref         TEXT               -- descrição da estrutura (tipo 3)
);

CREATE INDEX IF NOT EXISTS idx_pi_bloco ON prereq_item(bloco_id);
CREATE INDEX IF NOT EXISTS idx_pi_disc  ON prereq_item(disciplina_req_id);

-- -----------------------------------------------------------------------------
-- Equivalências: mesma semântica de blocos
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS equivalencia_bloco (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    disciplina_curriculo_id INTEGER NOT NULL
                            REFERENCES disciplina_curriculo(id) ON DELETE CASCADE,
    sie_item               INTEGER,
    sie_descricao          TEXT
);

CREATE INDEX IF NOT EXISTS idx_eb_dc ON equivalencia_bloco(disciplina_curriculo_id);

CREATE TABLE IF NOT EXISTS equivalencia_item (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    bloco_id              INTEGER NOT NULL
                            REFERENCES equivalencia_bloco(id) ON DELETE CASCADE,
    disciplina_req_id     INTEGER REFERENCES disciplina(id),
    disciplina_req_codigo TEXT,
    tipo_item             INTEGER,
    tipo                  TEXT,              -- "Disciplina Vencida"
    curriculo_ref         TEXT               -- "Curso - Ano" do disciplinaCurriculoRef
);

-- -----------------------------------------------------------------------------
-- Tabelas derivadas (Fase 6) — criadas já para não migrar depois
-- -----------------------------------------------------------------------------
-- Parecer de equivalência heurística entre duas disciplinas globais.
-- Regra do projeto: carga horária >= alvo E ementa >= 75% similar.
CREATE TABLE IF NOT EXISTS similaridade_ementa (
    disciplina_a   INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
    disciplina_b   INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
    score_cosine   REAL,                     -- TF-IDF na ementa
    score_jaccard  REAL,                     -- Jaccard de tokens do nome
    score_final    REAL,                     -- combinação calibrada
    ch_a           INTEGER,
    ch_b           INTEGER,
    veredito       TEXT,                     -- equivalente | revisar | nao_equivalente
    motivo         TEXT,                     -- o que pesou (regra de sufixo, CH, etc.)
    calculado_em   TEXT,
    PRIMARY KEY (disciplina_a, disciplina_b)
);

-- Quais disciplinas satisfazem cada curso (direto ou por equivalência).
CREATE TABLE IF NOT EXISTS cobertura_curso (
    curso_id      INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
    disciplina_id INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
    via           TEXT,                     -- direto | equivalencia | heuristica
    PRIMARY KEY (curso_id, disciplina_id)
);

-- Equivalências julgadas (Fase 6b). Tabela separada de propósito: o palpite da
-- heurística em `similaridade_ementa` nunca é sobrescrito.
CREATE TABLE IF NOT EXISTS equivalencia_julgada (
    disciplina_a  INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
    disciplina_b  INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
    veredito      TEXT NOT NULL,             -- equivalente | parcial | nao_equivalente
    confianca     REAL,
    justificativa TEXT,
    julgador      TEXT,
    julgado_em    TEXT,
    PRIMARY KEY (disciplina_a, disciplina_b)
);

-- Quais disciplinas podem preencher a cota de DCG de cada curso/estrutura.
-- `fonte`: menu = lista explícita do currículo; aberta = cota sem lista (qualquer
-- disciplina não-terminal, respeitando a situação).
CREATE TABLE IF NOT EXISTS dcg_elegivel (
    curso_id      INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
    estrutura_id  INTEGER NOT NULL REFERENCES estrutura(id) ON DELETE CASCADE,
    disciplina_id INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
    fonte         TEXT NOT NULL,             -- menu | aberta
    horas_cota    INTEGER,
    PRIMARY KEY (curso_id, estrutura_id, disciplina_id)
);

CREATE INDEX IF NOT EXISTS idx_dcg_curso ON dcg_elegivel(curso_id, estrutura_id);
CREATE INDEX IF NOT EXISTS idx_dcg_disc  ON dcg_elegivel(disciplina_id);

-- -----------------------------------------------------------------------------
-- Auditoria do otimizador (Fase 6c) — para alinhar Python e o front TS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rota_gulosa (
    ordem        INTEGER PRIMARY KEY,        -- posição na rota
    curso_id     INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
    horas_passo  INTEGER NOT NULL,
    horas_acum   INTEGER NOT NULL,
    semestre     INTEGER NOT NULL,
    disciplinas_novas INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rota_benchmark (
    base_curso_id  INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
    alvo_curso_id  INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
    horas          INTEGER NOT NULL,         -- custo marginal de fechar o alvo
    disciplinas    INTEGER NOT NULL,
    semestres      INTEGER NOT NULL,
    calculado_em   TEXT,
    PRIMARY KEY (base_curso_id, alvo_curso_id)
);

-- -----------------------------------------------------------------------------
-- Views de conveniência (para a dashboard e para queries exploratórias)
-- -----------------------------------------------------------------------------
-- Equivalência efetiva = o que o SIE declara + o que foi julgado equivalente.
-- É a view que o front deve consumir no lugar de `equivalencia_item`.
CREATE VIEW IF NOT EXISTS v_equivalencia_efetiva AS
SELECT dc.disciplina_id  AS alvo_id,
       ei.disciplina_req_id AS substituta_id,
       'oficial'         AS origem,
       1.0               AS confianca,
       'equivalente'     AS veredito
FROM equivalencia_item ei
JOIN equivalencia_bloco eb      ON eb.id = ei.bloco_id
JOIN disciplina_curriculo dc    ON dc.id = eb.disciplina_curriculo_id
WHERE ei.disciplina_req_id IS NOT NULL
  AND ei.disciplina_req_id <> dc.disciplina_id
UNION ALL
SELECT ej.disciplina_a, ej.disciplina_b, 'julgada', ej.confianca, ej.veredito
FROM equivalencia_julgada ej
WHERE ej.veredito IN ('equivalente', 'parcial')
UNION ALL
SELECT ej.disciplina_b, ej.disciplina_a, 'julgada', ej.confianca, ej.veredito
FROM equivalencia_julgada ej
WHERE ej.veredito IN ('equivalente', 'parcial');

CREATE VIEW IF NOT EXISTS v_disciplina_curriculo AS
SELECT
    dc.id                AS oferta_id,
    v.id                 AS versao_id,
    c.id                 AS curso_id,
    c.nome               AS curso,
    v.ano                AS versao_ano,
    v.situacao           AS versao_situacao,
    e.descricao          AS nucleo,
    e.ch_minima          AS nucleo_ch_minima,
    d.id                 AS disciplina_id,
    d.codigo             AS codigo,
    d.nome               AS disciplina,
    d.ch_total           AS ch,
    d.creditos           AS creditos,
    dc.tipo_item         AS tipo_item,
    dc.tipo              AS tipo,
    dc.periodo_ideal     AS periodo_ideal,
    dc.tem_prereq        AS tem_prereq,
    dc.tem_equiv         AS tem_equiv
FROM disciplina_curriculo dc
JOIN disciplina d          ON d.id = dc.disciplina_id
JOIN estrutura e           ON e.id = dc.estrutura_id
JOIN versao_curriculo v    ON v.id = dc.versao_id
JOIN curso c               ON c.id = v.curso_id;
