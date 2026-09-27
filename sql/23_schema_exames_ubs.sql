-- Limpeza LGPD dos exames (csv_exames → exames_ubs).
-- Sem nome/CPF/CNS/DNV/prontuário/nome do profissional.

USE vitacare_mvp;

CREATE TABLE IF NOT EXISTS exames_ubs (
    exame_id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id              VARCHAR(16)  NULL COMMENT 'P###### via map_paciente_chave',
    profissional_id          VARCHAR(16)  NULL COMMENT 'R###### solicitante via map (nome)',
    cnes                     VARCHAR(32)  NULL,
    unidade_de_saude         VARCHAR(255) NULL,
    ap                       VARCHAR(64)  NULL,
    sexo                     VARCHAR(32)  NULL,
    data_da_requisicao       VARCHAR(32)  NULL,
    codigo_da_tabela         VARCHAR(64)  NULL,
    nome_do_exame            VARCHAR(255) NULL,
    valor_do_exame           VARCHAR(64)  NULL COMMENT 'valor tabelado; não comprova pagamento',
    cid_ativo                VARCHAR(64)  NULL,
    cbo                      VARCHAR(255) NULL,
    categoria_profissional   VARCHAR(255) NULL,
    codigo_da_requisicao     VARCHAR(64)  NULL COMMENT 'não usar como PK; baixa cardinalidade na fonte',
    competencia_extracao     CHAR(7)      NOT NULL,
    carga_id                 BIGINT UNSIGNED NULL,
    linha_origem             INT UNSIGNED NULL,
    PRIMARY KEY (exame_id),
    KEY idx_ex_ubs_pac (paciente_id),
    KEY idx_ex_ubs_prof (profissional_id),
    KEY idx_ex_ubs_cnes (cnes),
    KEY idx_ex_ubs_exame (nome_do_exame(64)),
    KEY idx_ex_ubs_dt (data_da_requisicao),
    KEY idx_ex_ubs_comp (competencia_extracao)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
