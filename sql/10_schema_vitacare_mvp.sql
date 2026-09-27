-- Schema paralelo de carga bruta (todas as colunas/linhas, sem limpeza LGPD).
-- Tabelas csv_* são criadas dinamicamente pelo scripts/ingest/import_bruto.py.

CREATE DATABASE IF NOT EXISTS vitacare_mvp
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE vitacare_mvp;

CREATE TABLE IF NOT EXISTS carga_arquivo (
    carga_id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    fonte                VARCHAR(64)  NOT NULL COMMENT 'slug do tipo de CSV',
    tabela_destino       VARCHAR(128) NOT NULL,
    arquivo_nome         VARCHAR(255) NOT NULL,
    competencia_extracao CHAR(7)      NOT NULL COMMENT 'YYYY-MM no nome do arquivo',
    arquivo_sha256       CHAR(64)     NOT NULL,
    qtd_colunas          INT UNSIGNED NULL,
    qtd_lidas            INT UNSIGNED NULL,
    qtd_aceitas          INT UNSIGNED NULL,
    qtd_rejeitadas       INT UNSIGNED NULL,
    status               VARCHAR(32)  NOT NULL DEFAULT 'iniciada'
        COMMENT 'iniciada|concluida|falha',
    iniciado_em          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalizado_em        DATETIME     NULL,
    mensagem             VARCHAR(500) NULL COMMENT 'erro agregado sem PII',
    PRIMARY KEY (carga_id),
    UNIQUE KEY uk_carga_sha_fonte (fonte, arquivo_sha256),
    KEY idx_carga_comp (fonte, competencia_extracao),
    KEY idx_carga_tabela (tabela_destino)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS linha_rejeitada (
    rejeicao_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    carga_id        BIGINT UNSIGNED NOT NULL,
    fonte           VARCHAR(64)  NOT NULL,
    linha_origem    INT UNSIGNED NOT NULL,
    motivo_codigo   VARCHAR(64)  NOT NULL COMMENT 'ex.: Q_LINHA_MALFORMADA',
    linha_bruta     MEDIUMTEXT   NOT NULL,
    registrado_em   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rejeicao_id),
    KEY idx_rej_carga (carga_id),
    CONSTRAINT fk_rej_carga FOREIGN KEY (carga_id) REFERENCES carga_arquivo (carga_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
