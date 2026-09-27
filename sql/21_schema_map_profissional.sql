-- Mapa local de profissionais (csv_listagem_login → profissional_id).
-- map_* e fila_* NÃO exportar (contêm CPF/CNS/login/nome).
-- exp_profissional é candidata à exportação (sem PII).

USE vitacare_mvp;

CREATE TABLE IF NOT EXISTS map_profissional_chave (
    map_id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    chave_tipo       VARCHAR(16)  NOT NULL
        COMMENT 'cpf|cns|login|conselho|nome|orphan_row',
    chave_norm       VARCHAR(255) NOT NULL
        COMMENT 'chave normalizada (ambiente restrito; nome só p/ join consultas)',
    profissional_id  VARCHAR(16)  NOT NULL COMMENT 'ex.: R000001',
    regra_origem     VARCHAR(32)  NOT NULL,
    criado_em        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (map_id),
    UNIQUE KEY uk_map_prof_chave (chave_tipo, chave_norm),
    KEY idx_map_prof_id (profissional_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fila_profissional_conflito (
    conflito_id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    motivo_codigo       VARCHAR(64)  NOT NULL,
    profissional_id_a   VARCHAR(16)  NULL,
    profissional_id_b   VARCHAR(16)  NULL,
    chave_tipo          VARCHAR(16)  NULL,
    detalhe             VARCHAR(255) NULL COMMENT 'metadado sem PII',
    registrado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conflito_id),
    KEY idx_fila_prof_motivo (motivo_codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Dimensão profissional pseudonimizada (exportável).
CREATE TABLE IF NOT EXISTS exp_profissional (
    profissional_id       VARCHAR(16)  NOT NULL,
    regra_origem          VARCHAR(32)  NOT NULL,
    cbo_code              VARCHAR(16)  NULL,
    cbo_desig             VARCHAR(255) NULL,
    qtd_unidades          INT UNSIGNED NOT NULL DEFAULT 0,
    primeira_competencia  CHAR(7)      NULL,
    ultima_competencia    CHAR(7)      NULL,
    PRIMARY KEY (profissional_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
