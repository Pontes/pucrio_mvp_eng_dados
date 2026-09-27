-- Limpeza LGPD reduzida: csv_ficha_a_v2_ext → ficha_a_ubs (colunas essenciais).

USE vitacare_mvp;

DROP TABLE IF EXISTS ficha_a_ubs;

CREATE TABLE ficha_a_ubs (
    ficha_id                              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id                           VARCHAR(16)  NULL COMMENT 'P######',
    cnes                                  VARCHAR(32)  NULL,
    nome_unidade_de_saude                 VARCHAR(255) NULL,
    nome_equipe_de_saude                  VARCHAR(255) NULL,
    codigo_da_equipe_de_saude             VARCHAR(64)  NULL,
    codigo_ine_equipe_de_saude            VARCHAR(64)  NULL,
    data_cadastro                         VARCHAR(32)  NULL,
    data_ultima_atualizacao_do_cadastro   VARCHAR(32)  NULL,
    situacao_usuario                      VARCHAR(64)  NULL,
    obito                                 VARCHAR(32)  NULL,
    sexo                                  VARCHAR(32)  NULL,
    raca_cor                              VARCHAR(64)  NULL,
    nacionalidade                         VARCHAR(128) NULL,
    peso                                  VARCHAR(32)  NULL,
    altura                                VARCHAR(32)  NULL,
    escolaridade                          VARCHAR(128) NULL,
    competencia_extracao                  CHAR(7)      NOT NULL,
    PRIMARY KEY (ficha_id),
    KEY idx_ficha_pac (paciente_id),
    KEY idx_ficha_cnes (cnes),
    KEY idx_ficha_comp (competencia_extracao)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
