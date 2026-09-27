-- Limpeza LGPD das consultas (csv_consultas_cap → consultas_ubs).
-- Sem CPF/CNS/src_id/nome do profissional na saída.

USE vitacare_mvp;

CREATE TABLE IF NOT EXISTS consultas_ubs (
    consulta_id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id              VARCHAR(16)  NULL COMMENT 'P###### via map_paciente_chave',
    profissional_id          VARCHAR(16)  NULL COMMENT 'R###### via map_profissional_chave',
    cnes                     VARCHAR(32)  NULL,
    unidade                  VARCHAR(255) NULL,
    ine                      VARCHAR(64)  NULL,
    ap                       VARCHAR(64)  NULL,
    dt_consulta              VARCHAR(32)  NULL COMMENT 'data do evento',
    hora_consulta            VARCHAR(32)  NULL,
    cbo_presc                VARCHAR(255) NULL COMMENT 'categoria CBO (não identifica pessoa)',
    competencia_extracao     CHAR(7)      NOT NULL,
    carga_id                 BIGINT UNSIGNED NULL,
    linha_origem             INT UNSIGNED NULL,
    PRIMARY KEY (consulta_id),
    KEY idx_cons_ubs_pac (paciente_id),
    KEY idx_cons_ubs_prof (profissional_id),
    KEY idx_cons_ubs_cnes (cnes),
    KEY idx_cons_ubs_dt (dt_consulta),
    KEY idx_cons_ubs_comp (competencia_extracao)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
