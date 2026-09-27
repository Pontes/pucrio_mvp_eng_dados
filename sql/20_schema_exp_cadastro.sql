-- Limpeza LGPD do cadastro (csv_cadastro_usuario_cap → cadastro_pacientes_ubs).
-- map_* e fila_* ficam só no MySQL local (contêm chaves de identidade).
-- Tabelas de saída (Databricks): cadastro_pacientes_ubs (+ auxiliares sem PII).

USE vitacare_mvp;

-- Chaves locais → paciente_id (NÃO exportar).
CREATE TABLE IF NOT EXISTS map_paciente_chave (
    map_id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    chave_tipo       VARCHAR(16)  NOT NULL COMMENT 'cpf|cns|src_id|orphan_row',
    chave_norm       VARCHAR(64)  NOT NULL COMMENT 'documento/ID normalizado (ambiente restrito)',
    paciente_id      VARCHAR(16)  NOT NULL COMMENT 'ex.: P000001',
    regra_origem     VARCHAR(32)  NOT NULL COMMENT 'regra que gerou o paciente_id',
    criado_em        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (map_id),
    UNIQUE KEY uk_map_chave (chave_tipo, chave_norm),
    KEY idx_map_paciente (paciente_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Conflitos de identidade (sem payload pessoal; só códigos e IDs internos).
CREATE TABLE IF NOT EXISTS fila_identidade_conflito (
    conflito_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    motivo_codigo    VARCHAR(64)  NOT NULL COMMENT 'ex.: Q_CPF_CNS_DIVERGENTE',
    paciente_id_a    VARCHAR(16)  NULL,
    paciente_id_b    VARCHAR(16)  NULL,
    chave_tipo       VARCHAR(16)  NULL,
    detalhe          VARCHAR(255) NULL COMMENT 'metadado sem PII',
    registrado_em    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conflito_id),
    KEY idx_fila_motivo (motivo_codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Dimensão pessoa (pseudônimo). Grão: 1 linha por paciente_id.
-- faixa_etaria: única por paciente, idade na ultima_competencia global.
DROP TABLE IF EXISTS exp_paciente;
CREATE TABLE exp_paciente (
    paciente_id           VARCHAR(16) NOT NULL,
    regra_origem          VARCHAR(32) NOT NULL COMMENT 'cpf|cns|src_id|orphan_row',
    qtd_unidades          INT UNSIGNED NOT NULL DEFAULT 0,
    primeira_competencia  CHAR(7)     NULL,
    ultima_competencia    CHAR(7)     NULL,
    faixa_etaria          VARCHAR(16) NULL
        COMMENT 'faixas de 10 anos; idade na ultima_competencia do paciente',
    PRIMARY KEY (paciente_id),
    KEY idx_exp_pac_faixa (faixa_etaria)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Cadastro limpo paciente × UBS. Grão: 1 linha por (paciente_id, cnes).
-- Competências: janela primeira/última; atributos do snapshot mais recente.
-- Nome canônico de exportação para o Databricks.
DROP TABLE IF EXISTS exp_cadastro_vinculo;
DROP TABLE IF EXISTS cadastro_pacientes_usb;
DROP TABLE IF EXISTS cadastro_pacientes_ubs;
CREATE TABLE cadastro_pacientes_ubs (
    paciente_id              VARCHAR(16)  NOT NULL,
    cnes                     VARCHAR(32)  NOT NULL,
    estab_saude              VARCHAR(255) NULL,
    ine                      VARCHAR(64)  NULL,
    bairro                   VARCHAR(255) NULL,
    sexo                     VARCHAR(32)  NULL,
    faixa_etaria             VARCHAR(16)  NULL
        COMMENT 'faixas de 10 anos (ex.: 30-39); idade na ultima_competencia',
    auxilio_brasil           VARCHAR(64)  NULL,
    primeira_competencia     CHAR(7)      NOT NULL,
    ultima_competencia       CHAR(7)      NOT NULL,
    qtd_competencias         INT UNSIGNED NOT NULL DEFAULT 1,
    PRIMARY KEY (paciente_id, cnes),
    KEY idx_cad_ubs_cnes (cnes),
    KEY idx_cad_ubs_bairro (bairro(64)),
    KEY idx_cad_ubs_faixa (faixa_etaria),
    KEY idx_cad_ubs_comp (ultima_competencia)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Presença por competência (migração / multiunidade no tempo).
-- Grão: 1 linha por (paciente_id, cnes, competencia_extracao).
CREATE TABLE IF NOT EXISTS exp_cadastro_presenca (
    paciente_id              VARCHAR(16) NOT NULL,
    cnes                     VARCHAR(32) NOT NULL,
    competencia_extracao     CHAR(7)     NOT NULL,
    PRIMARY KEY (paciente_id, cnes, competencia_extracao),
    KEY idx_presenca_comp (competencia_extracao),
    KEY idx_presenca_cnes (cnes)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
